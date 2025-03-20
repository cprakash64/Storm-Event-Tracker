#!/usr/bin/env python3
"""
manager.py

This script implements the "tracker" or "manager" process in our DHT system.
It:
  - Listens on a UDP port for peer registrations
  - Assigns peer IDs
  - Maintains a ring topology by sorting peers and setting each peer's "next_peer"
  - Loads and distributes CSV event data to peers
  - Handles peer leave events
  - Supports teardown for graceful shutdown
"""

import socket
import threading
import json
import csv
import sys
import os

# Configuration
MANAGER_HOST = '127.0.0.1'
MANAGER_PORT = 5000
CSV_FILE = "StormEvents_locations-ftp_v1.0_d2024_c20250317.csv"

class Manager:
    """
    The Manager class:
      - Maintains a mapping of peer_id -> (peer_address, peer_port)
      - Provides console commands to set up the ring, distribute data, and teardown
      - Loads events from a CSV file
      - Distributes events using a hash-based assignment
    """
    def __init__(self, host=MANAGER_HOST, port=MANAGER_PORT):
        self.host = host
        self.port = port
        # Mapping: peer_id -> (peer_address, peer_port)
        self.peers = {}
        self.next_peer_id = 0
        self.running = True
        self.events = []  # Will store event rows from CSV
        self.lock = threading.Lock()

        # Create and bind the UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        print(f"Manager started on {self.host}:{self.port}")

    def load_csv(self):
        """Load CSV data into self.events if the file exists."""
        if not os.path.exists(CSV_FILE):
            print(f"CSV file {CSV_FILE} not found.")
            return
        try:
            with open(CSV_FILE, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    self.events.append(row)
            print(f"Loaded {len(self.events)} events from {CSV_FILE}.")
        except Exception as e:
            print("Error loading CSV:", e)

    def run(self):
        """Main loop to receive and handle incoming UDP messages. Also starts a console thread."""
        # Start a separate thread to handle console commands
        threading.Thread(target=self.console_thread, daemon=True).start()

        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                message = json.loads(data.decode())
                self.handle_message(message, addr)
            except Exception as e:
                print("Error in manager run loop:", e)

    def handle_message(self, message, addr):
        """Handle incoming messages from peers."""
        command = message.get("command")
        if command == "register":
            self.register_peer(message, addr)
        elif command == "store_ack":
            # A peer acknowledges it stored an event
            peer_id = message.get("peer_id")
            event_id = message.get("event_id")
            print(f"[Manager] Received store_ack from peer {peer_id} for event {event_id}")
        elif command == "leave":
            self.remove_peer(message, addr)
        else:
            print("[Manager] Unknown command received:", command)

    def register_peer(self, message, addr):
        """
        Assign a new peer_id, store the peer's (address, port) in self.peers,
        and reply with 'set_id'.
        """
        peer_port = message.get("peer_port")
        peer_address = addr[0]
        with self.lock:
            peer_id = self.next_peer_id
            self.next_peer_id += 1
            self.peers[peer_id] = (peer_address, peer_port)

        print(f"[Manager] Registered peer {peer_id} at {peer_address}:{peer_port}")
        response = {"command": "set_id", "peer_id": peer_id}
        self.sock.sendto(json.dumps(response).encode(), addr)

    def remove_peer(self, message, addr):
        """
        A peer notifies the manager it is leaving. Remove it from self.peers
        and update the ring.
        """
        peer_id = message.get("peer_id")
        with self.lock:
            if peer_id in self.peers:
                del self.peers[peer_id]
                print(f"[Manager] Peer {peer_id} removed. Updating ring...")
                self.update_ring()
            else:
                print(f"[Manager] Attempt to remove unknown peer {peer_id}")

    def update_ring(self):
        """
        Recompute the ring by sorting peers by ID and sending each peer
        a 'set_next_peer' message to point to the next peer in the ring.
        """
        with self.lock:
            sorted_peers = sorted(self.peers.items(), key=lambda x: x[0])
        n = len(sorted_peers)
        if n == 0:
            print("[Manager] No peers to update in ring.")
            return

        for i, (peer_id, (address, port)) in enumerate(sorted_peers):
            next_index = (i + 1) % n
            next_peer = sorted_peers[next_index][1]  # (address, port)
            msg = {"command": "set_next_peer", "next_peer": list(next_peer)}
            try:
                self.sock.sendto(json.dumps(msg).encode(), (address, port))
                print(f"[Manager] For peer {peer_id}, set next peer to {next_peer}")
            except Exception as e:
                print(f"[Manager] Error sending set_next_peer to peer {peer_id}:", e)

    def distribute_events(self):
        """
        Distribute loaded CSV events to peers by hashing the event's ID
        to decide which peer gets each event.
        """
        with self.lock:
            if not self.peers:
                print("[Manager] No peers registered. Cannot distribute events.")
                return
            sorted_peer_ids = sorted(self.peers.keys())
            num_peers = len(sorted_peer_ids)

        print("[Manager] Distributing events to peers...")
        for event in self.events:
            # Use 'EVENT_ID' from the CSV if present; otherwise fall back to hashing the entire row.
            key = event.get("EVENT_ID")
            if key is None:
                key = hash(str(event))
            # Convert to string if needed
            key_str = str(key)

            # Assign to a peer based on the hash of the event_id
            assigned_index = hash(key_str) % num_peers
            assigned_peer_id = sorted_peer_ids[assigned_index]
            assigned_peer = self.peers[assigned_peer_id]
            msg = {
                "command": "store",
                "event_id": key_str,
                "event_data": event
            }
            try:
                self.sock.sendto(json.dumps(msg).encode(), assigned_peer)
            except Exception as e:
                print(f"[Manager] Error sending store to peer {assigned_peer_id}:", e)

        print("[Manager] Distribution complete.")

    def console_thread(self):
        """
        A separate thread to accept console commands:
          - setup: run update_ring
          - distribute: distribute events to peers
          - teardown: shut down all peers
        """
        while self.running:
            try:
                cmd = input("Manager command (setup, distribute, teardown): ").strip()
                if cmd == "setup":
                    self.update_ring()
                elif cmd == "distribute":
                    self.distribute_events()
                elif cmd == "teardown":
                    self.teardown()
                else:
                    print("Unknown command. Available: setup, distribute, teardown")
            except Exception as e:
                print("Error in console thread:", e)

    def teardown(self):
        """Send a 'teardown' command to all peers, then stop running."""
        with self.lock:
            for peer_id, (address, port) in self.peers.items():
                msg = {"command": "teardown"}
                try:
                    self.sock.sendto(json.dumps(msg).encode(), (address, port))
                except Exception as e:
                    print(f"[Manager] Error sending teardown to peer {peer_id}:", e)
        self.running = False
        print("[Manager] Shutting down.")

if __name__ == "__main__":
    manager = Manager()
    # Load CSV data (if available)
    manager.load_csv()

    try:
        manager.run()
    except KeyboardInterrupt:
        print("Keyboard interrupt received, shutting down.")
        manager.teardown()
        sys.exit(0)
