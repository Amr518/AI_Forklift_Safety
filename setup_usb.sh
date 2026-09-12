#!/bin/bash
echo "=== Setting up Relay & udev rules ==="
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="forklift_relay", MODE="0666"' | sudo tee /etc/udev/rules.d/99-forklift-relay.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
echo "=== Successfully activated! ==="
