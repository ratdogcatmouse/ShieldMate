#!/bin/bash
VM="192.168.137.106"   # target agent laptop IP
USER_ACCT="shieldtest"

for i in $(seq 1 20); do
    echo "$(date +%H:%M:%S)  attempt ${i}"
    smbutil view "//${USER_ACCT}:WrongPass${i}@${VM}" 2>&1 | tail -1 &
done
wait

echo ""
echo "--- Post-block verification ---"
smbutil view "//${USER_ACCT}:WrongPassFinal@${VM}" 2>&1
