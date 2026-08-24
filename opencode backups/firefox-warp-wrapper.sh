#!/bin/bash
exec sudo ip netns exec warp-1 /home/alan/.cache/ms-playwright/firefox-1532/firefox/firefox "$@"
