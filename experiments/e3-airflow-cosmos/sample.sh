#!/bin/sh
# run on PVE host: samples CT 198 every 30 s for $1 minutes
out=/root/e3/stats.csv; cg=/sys/fs/cgroup/lxc/198
echo "ts,ct_mem_current_mb,ct_mem_peak_mb,container,mem_usage,cpu" > $out
end=$(( $(date +%s) + $1 * 60 ))
while [ $(date +%s) -lt $end ]; do
  ts=$(date -Is); cur=$(( $(cat $cg/memory.current) / 1048576 )); pk=$(( $(cat $cg/memory.peak) / 1048576 ))
  pct exec 198 -- docker stats --no-stream --format '{{.Name}},{{.MemUsage}},{{.CPUPerc}}' | sed "s|^|$ts,$cur,$pk,|" >> $out
  sleep 30
done
echo done >> /root/e3/sample.done
