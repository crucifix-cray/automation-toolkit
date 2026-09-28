export GITHUB_TOKEN=__GH_TOKEN__
export LOV_JID={{JID}}
export LOV_DOMAIN_INDEX=""
curl -fsSL https://raw.githubusercontent.com/crucifix-cray/automation-toolkit/main/docker/vps_worker/job_lovable.sh -o /app/job.sh \
  && chmod +x /app/job.sh \
  && nohup bash /app/job.sh >/dev/null 2>&1 & disown
echo STARTED jid={{JID}}
