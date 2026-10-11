# T03b rolling64 GPU packet

This packet uses candidate `dc951c6918ae0fab4ef8f6152c6de198f0f7f858`. Default-off T16 history remains separate. The sealed admission pins `CURRENT_MANIFEST.json`; controller publishes canonical `{pid,start_ticks,execution_id}` and the child verifies it with D07 before locking. Six services and 24 calls are bounded to 2400 seconds work plus 300 seconds cleanup; each service generation phase is capped at 1500 seconds. First `not_met` stops later arms.

CPU proof is `CPU_PROOF_CURRENT.json`. FILEdry: `PYTHONPATH=. /data2/FreeToken/venv/bin/python runner.py --filedry`. After independent review, root runs `runner.py --run --admission <sealed-path>`.
