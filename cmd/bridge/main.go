package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

var (
	listenAddr = flag.String("listen", ":3334", "WSS listen address")
	poolURL    = flag.String("pool", "pool.supportxmr.com:3333", "Upstream pool host:port")
	wallet     = flag.String("wallet", "", "Wallet address")
	healthPort = flag.String("health", ":8081", "Health check port")
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
		log.Fatal(http.ListenAndServe(*healthPort, nil))
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
	<-ctx.Done()
	log.Println("Shutting down...")
}

func handleWS(ctx context.Context, ws *websocket.Conn) {
	atomic.AddInt64(&connCount, 1)
	defer atomic.AddInt64(&connCount, -1)
	defer ws.Close()

	// Connect to upstream pool
	dialer := &net.Dialer{Timeout: 15 * time.Second}
	conn, err := dialer.DialContext(ctx, "tcp", os.Getenv("POOL_HOST")+":"+os.Getenv("POOL_PORT"))
	if err != nil {
		log.Printf("Pool connect failed: %v", err)
		return
	}
	defer conn.Close()

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