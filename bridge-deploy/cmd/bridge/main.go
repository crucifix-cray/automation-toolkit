package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

var (
	listenAddr = flag.String("listen", "", "WSS listen address (default: $PORT)")
	poolURL    = flag.String("pool", "pool.supportxmr.com:3333", "Upstream pool host:port")
	wallet     = flag.String("wallet", "", "Wallet address")
	healthPort = flag.String("health", "", "Health check port (default: $HEALTH_PORT)")
)

var (
	connCount  int64
	shareCount int64
	accepted   int64
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

func main() {
	flag.Parse()
	if *listenAddr == "" {
		if p := os.Getenv("PORT"); p != "" {
			*listenAddr = ":" + p
		} else {
			*listenAddr = ":3334"
		}
	}
	if hp := os.Getenv("HEALTH_PORT"); hp != "" {
		if !strings.Contains(hp, ":") {
			hp = ":" + hp
		}
		*healthPort = hp
	}
	if *wallet == "" {
		log.Fatal("wallet required")
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	// Health endpoint
	go func() {
		http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
			fmt.Fprintf(w, `{"connections":%d,"shares":%d,"accepted":%d}`,
				atomic.LoadInt64(&connCount), atomic.LoadInt64(&shareCount), atomic.LoadInt64(&accepted))
		})
		http.HandleFunc("/stats", func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]int64{
				"connections": atomic.LoadInt64(&connCount),
				"shares":      atomic.LoadInt64(&shareCount),
				"accepted":    atomic.LoadInt64(&accepted),
			})
		})
		if err := http.ListenAndServe(*healthPort, nil); err != nil {
			log.Printf("health server stopped: %v", err)
		}
	}()

	upgrader.CheckOrigin = func(r *http.Request) bool { return true }

	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		ws, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("upgrade error: %v", err)
			return
		}
		go handleWS(ctx, ws)
	})

	log.Printf("WSS bridge listening on %s -> %s via Tor", *listenAddr, *poolURL)

	// Start the HTTP server (handlers above do nothing until this runs).
	srv := &http.Server{Addr: *listenAddr}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen failed: %v", err)
		}
	}()

	go warmPool(os.Getenv("POOL_HOST") + ":" + os.Getenv("POOL_PORT"))

	<-ctx.Done()
	shutdown, done := context.WithTimeout(context.Background(), 5*time.Second)
	defer done()
	_ = srv.Shutdown(shutdown)
	log.Println("Shutting down...")
}

// dialPool opens a TCP connection to the pool, optionally through a SOCKS5
// proxy (Tor). Direct egress from Railway is blocklisted by the pool, so the
// SOCKS path is the default when TOR_SOCKS is set.
func dialPool(ctx context.Context, network, addr string) (net.Conn, error) {
	socksAddr := os.Getenv("TOR_SOCKS")
	if socksAddr == "" {
		d := &net.Dialer{Timeout: 15 * time.Second}
		return d.DialContext(ctx, network, addr)
	}
	return dialSOCKS5(ctx, socksAddr, addr)
}

// dialSOCKS5 performs a minimal SOCKS5 CONNECT handshake.
func dialSOCKS5(ctx context.Context, proxyAddr, target string) (net.Conn, error) {
	d := &net.Dialer{Timeout: 20 * time.Second}
	conn, err := d.DialContext(ctx, "tcp", proxyAddr)
	if err != nil {
		return nil, fmt.Errorf("socks dial: %w", err)
	}
	// Tor builds a circuit on first use of a destination; allow generous time.
	_ = conn.SetDeadline(time.Now().Add(150 * time.Second))
	// greeting: version 5, 1 method, no-auth
	if _, err := conn.Write([]byte{0x05, 0x01, 0x00}); err != nil {
		conn.Close()
		return nil, err
	}
	resp := make([]byte, 2)
	if _, err := io.ReadFull(conn, resp); err != nil {
		conn.Close()
		return nil, err
	}
	if resp[0] != 0x05 || resp[1] != 0x00 {
		conn.Close()
		return nil, fmt.Errorf("socks auth failed: %v", resp)
	}
	// CONNECT request with domain name
	host, portStr, _ := net.SplitHostPort(target)
	port, _ := strconv.Atoi(portStr)
	req := []byte{0x05, 0x01, 0x00, 0x03, byte(len(host))}
	req = append(req, host...)
	req = append(req, byte(port>>8), byte(port&0xff))
	if _, err := conn.Write(req); err != nil {
		conn.Close()
		return nil, err
	}
	head := make([]byte, 4)
	if _, err := io.ReadFull(conn, head); err != nil {
		conn.Close()
		return nil, err
	}
	if head[1] != 0x00 {
		conn.Close()
		return nil, fmt.Errorf("socks connect refused: %d", head[1])
	}
	// drain bound address
	switch head[3] {
	case 0x01:
		_, _ = io.CopyN(io.Discard, conn, 4)
	case 0x03:
		l := make([]byte, 1)
		_, _ = io.ReadFull(conn, l)
		_, _ = io.CopyN(io.Discard, conn, int64(l[0]))
	case 0x04:
		_, _ = io.CopyN(io.Discard, conn, 16)
	}
	_, _ = io.CopyN(io.Discard, conn, 2)
	_ = conn.SetDeadline(time.Time{})
	return conn, nil
}

// warmPool builds the Tor circuit to the pool up-front so the first real
// worker doesn't eat a 60s circuit-build stall.
func warmPool(target string) {
	deadline := time.Now().Add(3 * time.Minute)
	for time.Now().Before(deadline) {
		ctx, cancel := context.WithTimeout(context.Background(), 150*time.Second)
		c, err := dialPool(ctx, "tcp", target)
		cancel()
		if err == nil {
			// Read the greeting so the circuit is genuinely usable.
			_ = c.SetReadDeadline(time.Now().Add(20 * time.Second))
			buf := make([]byte, 1)
			_, _ = c.Read(buf)
			c.Close()
			log.Printf("pool circuit warm via Tor (%s)", target)
			return
		}
		log.Printf("warmup attempt failed: %v", err)
		time.Sleep(5 * time.Second)
	}
	log.Printf("pool warmup gave up; will retry per connection")
}

func handleWS(ctx context.Context, ws *websocket.Conn) {
	atomic.AddInt64(&connCount, 1)
	defer atomic.AddInt64(&connCount, -1)
	defer ws.Close()

	target := os.Getenv("POOL_HOST") + ":" + os.Getenv("POOL_PORT")
	conn, err := dialPool(ctx, "tcp", target)
	if err != nil {
		log.Printf("Pool connect failed: %v", err)
		return
	}
	defer conn.Close()
	log.Printf("pool connected via %s", map[bool]string{true: "tor", false: "direct"}[os.Getenv("TOR_SOCKS") != ""])

	var wg sync.WaitGroup
	wg.Add(2)

	// WS -> Pool
	go func() {
		defer wg.Done()
		defer conn.Close()
		for {
			_, msg, err := ws.ReadMessage()
			if err != nil {
				return
			}
			conn.Write(append(msg, '\n'))
		}
	}()

	// Pool -> WS
	go func() {
		defer wg.Done()
		buf := make([]byte, 8192)
		for {
			n, err := conn.Read(buf)
			if err != nil {
				return
			}
			ws.WriteMessage(websocket.TextMessage, buf[:n])
		}
	}()

	wg.Wait()
}