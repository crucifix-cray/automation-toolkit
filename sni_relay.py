#!/usr/bin/env python3
import socket, struct, threading, select
SOCKS_HOST='127.0.0.1'
SOCKS_PORT=1080
LISTEN_HTTP='127.0.0.1'
LISTEN_HTTP_PORT=80
LISTEN_HTTPS='127.0.0.1'
LISTEN_HTTPS_PORT=443
def get_sni(data):
    try:
        if len(data)<43 or data[0]!=0x16: return None
        pos=data.find(b'\x00\x00')
        while pos!=-1:
            if pos+4 < len(data):
                try:
                    ext_len=struct.unpack('!H', data[pos+2:pos+4])[0]
                    if pos+4+ext_len <= len(data) and data[pos+4]==0x00:
                        name_len=struct.unpack('!H', data[pos+7:pos+9])[0]
                        if pos+9+name_len <= len(data):
                            sni=data[pos+9:pos+9+name_len].decode()
                            if '.' in sni and len(sni)<253:
                                return sni
                except: pass
            pos=data.find(b'\x00\x00', pos+1)
        return None
    except: return None
def socks5_connect(dst_ip, dst_port):
    s=socket.socket()
    s.settimeout(10)
    s.connect((SOCKS_HOST, SOCKS_PORT))
    s.sendall(b'\x05\x01\x00')
    resp=s.recv(2)
    if resp!=b'\x05\x00': raise Exception(f'handshake {resp.hex()}')
    ip_bytes=socket.inet_aton(dst_ip)
    port_bytes=struct.pack('!H', dst_port)
    req=b'\x05\x01\x00\x01'+ip_bytes+port_bytes
    s.sendall(req)
    resp=s.recv(10)
    if len(resp)<2 or resp[1]!=0x00: raise Exception(f'connect {resp.hex() if resp else "no resp"}')
    return s
def handle_client(client):
    try:
        client.settimeout(5)
        data=client.recv(4096, socket.MSG_PEEK)
        if not data:
            client.close(); return
        sni=get_sni(data)
        if not sni:
            try:
                txt=data.decode(errors='ignore')
                if 'Host:' in txt:
                    for line in txt.split('\r\n'):
                        if line.lower().startswith('host:'):
                            sni=line.split(':',1)[1].strip().split(':')[0]
                            break
            except: pass
        if not sni:
            print(f'no SNI {data[:30]}', flush=True)
            client.close(); return
        print(f'ACCEPT {client.getpeername()} SNI {sni}', flush=True)
        try:
            infos=socket.getaddrinfo(sni, 443, socket.AF_INET, socket.SOCK_STREAM)
            dst_ip=infos[0][4][0]
            print(f'DNS {sni} -> {dst_ip}', flush=True)
        except Exception as e:
            print(f'DNS fail {sni} {e}', flush=True)
            client.close(); return
        try:
            remote=socks5_connect(dst_ip, 443)
            print(f'SOCKS ATYP=1 DST={dst_ip}:443 REP=0', flush=True)
        except Exception as e:
            print(f'SOCKS fail {sni} {e}', flush=True)
            client.close(); return
        print(f'PIPE START {sni}', flush=True)
        client.setblocking(False)
        remote.setblocking(False)
        total_c2r=0; total_r2c=0
        while True:
            r,_,e=select.select([client, remote], [], [client, remote], 10)
            if not r: break
            for sock in r:
                try:
                    d=sock.recv(4096)
                    if not d: raise Exception('closed')
                    if sock is client:
                        remote.sendall(d)
                        total_c2r+=len(d)
                    else:
                        client.sendall(d)
                        total_r2c+=len(d)
                except: raise
        print(f'PIPE END {sni} C2R={total_c2r} R2C={total_r2c}', flush=True)
        client.close(); remote.close()
    except Exception as e:
        try: print(f'handle error {e}', flush=True)
        except: pass
        try: client.close()
        except: pass
def main():
    s_https=socket.socket()
    s_https.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s_https.bind((LISTEN_HTTPS, LISTEN_HTTPS_PORT))
    s_https.listen(100)
    s_http=socket.socket()
    s_http.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s_http.bind((LISTEN_HTTP, LISTEN_HTTP_PORT))
    s_http.listen(100)
    print(f'LISTEN {LISTEN_HTTPS}:{LISTEN_HTTPS_PORT} and {LISTEN_HTTP}:{LISTEN_HTTP_PORT} -> socks5://{SOCKS_HOST}:{SOCKS_PORT} ATYP=1', flush=True)
    while True:
        r,_,_=select.select([s_https, s_http], [], [])
        for ls in r:
            client,addr=ls.accept()
            print(f'ACCEPT {addr}', flush=True)
            threading.Thread(target=handle_client, args=(client,), daemon=True).start()
if __name__=='__main__':
    main()
