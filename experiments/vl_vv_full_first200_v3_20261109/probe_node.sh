#!/bin/bash
# Read-only check of an owned allocation: its own CPU use over 10 s, memory, CPU set, API reachability.
cg=$(awk -F: '{print $3}' /proc/self/cgroup | head -1)
job=$(echo "$cg" | sed -E 's#(.*/job_[0-9]+).*#\1#')
d=/sys/fs/cgroup$job
u1=$(awk '/usage_usec/{print $2}' $d/cpu.stat); sleep 10; u2=$(awk '/usage_usec/{print $2}' $d/cpu.stat)
mc=$(cat $d/memory.current); mm=$(cat $d/memory.max)
api=$(curl -s -o /dev/null -m 15 -w "%{http_code} %{time_total}s" https://api.openai.com/v1/models)
echo "host=$(hostname) job=${job##*/} cpus=$(cat $d/cpuset.cpus.effective) busy_cpus=$(python3 -c "print(round(($u2-$u1)/1e7,2))") mem_used_GiB=$((mc/1073741824)) mem_max=$mm api=$api"
