#!/bin/bash
# Clean shutdown of FreeToken test server
PID_FILE="/data2/FreeToken/qwen38_eval.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Gracefully terminating FreeToken server PID $PID..."
        kill -15 "$PID"
        for i in {1..15}; do
            if kill -0 "$PID" 2>/dev/null; then
                sleep 1
            else
                break
            fi
        done
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing PID $PID..."
            kill -9 "$PID"
        fi
    fi
    rm -f "$PID_FILE"
fi

# Fallback: kill by port 8095 if bound
fuser -k -15 8095/tcp 2>/dev/null || true
sleep 2
fuser -k -9 8095/tcp 2>/dev/null || true
echo "FreeToken server stopped. Verifying port 8095:"
ss -tulpn | grep 8095 || echo "Port 8095 is clean."
