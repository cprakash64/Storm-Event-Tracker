#!/usr/bin/env python3
"""
peer.py

This script implements a peer (DHT node) that:
  - Registers with the manager
  - Stores events (via 'store' command)
  - Forwards queries ('find_event') to the next peer in the ring
  - Responds with 'found_event' if it has the data
  - Can 'leave' (notify manager of departure)
  - Shuts down gracefully on 'teardown'
"""

import socket
import threading
import json
import sys

MANAGER_ADDRESS = ('127.0.0.1', 5000)

class Peer:
    """
    The Peer class:
      - Registers with the manager
      - Stores assigned events
      - Handles queries across the ring
      - Maintains a pointer to the next peer (IP, port)
    """
    def __init__(self, p_port):
        self.p_port = p_port              # UDP port for this peer
        self.peer_id = None               # Assigned by the manager
        self.manager_address = MANAGER_ADDRESS
        self.running = True
        self.data_store = {}              # event_id -> event_data
        self.next_peer = None             # (ip, port) for next peer in ring
        self.lock = threading.Lock()

        # Create and bind the UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', self.p_port))
        print(f"[Peer] Started on port {self.p_port}")

    def register_with_manager(self):
        """Send a 'register' command to the manager and wait for the 'set_id' response."""
        msg = {"command": "register", "peer_port": self.p_port}
        self.sock.sendto(json.dumps(msg).encode(), self.manager_address)

        data, addr = self.sock.recvfrom(4096)
        response = json.loads(data.decode())
        if response.get("command") == "set_id":
            self.peer_id = response.get("peer_id")
            print(f"[Peer] Registered with manager. Assigned ID: {self.peer_id}")
        else:
            print("[Peer] Unexpected response from manager:", response)

    def listen(self):
        """Background thread that listens for incoming UDP messages."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                message = json.loads(data.decode())
                self.handle_message(message, addr)
            except Exception as e:
                print("[Peer] Error in listening thread:", e)

    def handle_message(self, message, addr):
        """
        Handle commands:
          - store
          - find_event
          - found_event
          - set_next_peer
          - teardown
          - set_id (usually only once, during registration)
        """
        command = message.get("command")
        if command == "store":
            self.handle_store(message)
        elif command == "find_event":
            self.handle_find_event(message, addr)
        elif command == "found_event":
            self.handle_found_event(message)
        elif command == "set_next_peer":
            self.handle_set_next_peer(message)
        elif command == "teardown":
            self.handle_teardown()
        elif command == "set_id":
            # Normally handled right after registration; ignoring duplicates
            pass
        else:
            print(f"[Peer {self.peer_id}] Unknown command: {command}")

    def handle_store(self, message):
        """Store an event locally, then send a store_ack to the manager."""
        event_id = message.get("event_id")
        event_data = message.get("event_data")
        self.store_event(event_id, event_data)

        # Acknowledge to manager
        ack = {
            "command": "store_ack",
            "peer_id": self.peer_id,
            "event_id": event_id
        }
        self.sock.sendto(json.dumps(ack).encode(), self.manager_address)

    def handle_find_event(self, message, addr):
        """Look up event locally; if not found, forward to next peer."""
        event_id = message.get("event_id")
        if event_id in self.data_store:
            # Found it locally
            response = {
                "command": "found_event",
                "event_id": event_id,
                "event_data": self.data_store[event_id]
            }
            self.sock.sendto(json.dumps(response).encode(), addr)
        else:
            # Not found, forward if next peer is known
            if self.next_peer:
                print(f"[Peer {self.peer_id}] Forwarding query for event {event_id} to {self.next_peer}")
                self.sock.sendto(json.dumps(message).encode(), self.next_peer)
            else:
                print(f"[Peer {self.peer_id}] Event {event_id} not found and no next peer set.")

    def handle_found_event(self, message):
        """We received a found_event response; display it to the user."""
        event_id = message.get("event_id")
        event_data = message.get("event_data")
        print(f"[Peer {self.peer_id}] Found event {event_id}: {event_data}")

    def handle_set_next_peer(self, message):
        """Update the next peer in the ring."""
        self.next_peer = tuple(message.get("next_peer"))
        print(f"[Peer {self.peer_id}] Next peer set to {self.next_peer}")

    def handle_teardown(self):
        """Shut down this peer."""
        self.running = False
        print(f"[Peer {self.peer_id}] Received teardown command. Shutting down.")

    def store_event(self, event_id, event_data):
        """Thread-safe local storage of an event."""
        with self.lock:
            self.data_store[event_id] = event_data
        print(f"[Peer {self.peer_id}] Stored event {event_id}")

    def query_event(self, event_id):
        """
        Initiate a query for event_id. If next_peer is set, forward 'find_event'.
        Otherwise, handle locally (which will likely fail if we don't have it).
        """
        msg = {"command": "find_event", "event_id": event_id}
        if self.next_peer:
            print(f"[Peer {self.peer_id}] Sending query for event {event_id} to next peer {self.next_peer}")
            self.sock.sendto(json.dumps(msg).encode(), self.next_peer)
        else:
            print("[Peer] Next peer not set. Checking locally.")
            self.handle_message(msg, None)

    def send_leave(self):
        """Notify the manager that this peer is leaving the ring."""
        if self.peer_id is not None:
            msg = {"command": "leave", "peer_id": self.peer_id}
            self.sock.sendto(json.dumps(msg).encode(), self.manager_address)
        self.running = False

    def start(self):
        """
        - Register with the manager
        - Start a background listener thread
        - Provide a simple console interface for user commands
        """
        self.register_with_manager()
        listener_thread = threading.Thread(target=self.listen, daemon=True)
        listener_thread.start()

        while self.running:
            try:
                user_input = input("Enter command (query <event_id> / leave / exit): ").strip()
                if user_input == "exit":
                    self.running = False
                    break
                elif user_input.startswith("query"):
                    parts = user_input.split()
                    if len(parts) == 2:
                        _, event_id = parts
                        self.query_event(event_id)
                    else:
                        print("Usage: query <event_id>")
                elif user_input == "leave":
                    self.send_leave()
                else:
                    print("Unknown command.")
            except Exception as e:
                print("[Peer] Error in main loop:", e)

        print(f"[Peer {self.peer_id}] Exiting.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python peer.py <peer_port>")
        sys.exit(1)
    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Port must be an integer.")
        sys.exit(1)

    peer = Peer(port)
    try:
        peer.start()
    except KeyboardInterrupt:
        print("[Peer] Keyboard interrupt, shutting down peer.")
