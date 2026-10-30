# stress-kit

Multi-vector load generator for stress testing **your own** infrastructure.

## Methods

http, syn, connect, udp, slowloris, rudy, icmp

## Usage

```bash
python3 stress.py <target> -p 80 -t 200 -d 60 -m http syn udp --confirm
```

`--confirm` is mandatory — target must be yours or authorized.

## Run wrapper

```bash
./run.sh 10.0.0.5 80 400 60 "http syn udp slowloris"
```

## Notes

- SYN/ICMP need root (or CAP_NET_RAW).
- Threads split evenly across methods.
- Stats: sent / errs / bytes / rate.
