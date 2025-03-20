# DHT Storm Event Tracker

A **Distributed Hash Table (DHT)** project that uses a **Manager** (tracker) process and multiple **Peer** processes to store and query storm events from a CSV file. Communication is done via **UDP** sockets, and the ring topology is maintained by the Manager.

## Table of Contents

1. [Overview](#overview)  
2. [Features](#features)  
3. [Requirements](#requirements)  
4. [File Structure](#file-structure)  
5. [Setup & Installation](#setup--installation)  
6. [Usage](#usage)  
7. [Commands](#commands)  
8. [Demo Steps](#demo-steps)  
9. [License](#license)  

---

## Overview

- **Manager** (`manager.py`):
  - Loads storm event data from a CSV file.
  - Listens for **peer registrations** and assigns each peer a unique ID.
  - Forms a **ring** of peers by sorting them by ID and telling each peer its next neighbor.
  - Distributes events among peers using a **hash function** on the `EVENT_ID`.
  - Can instruct all peers to **tear down**.

- **Peer** (`peer.py`):
  - Registers with the Manager to receive a unique ID.
  - Maintains a local data store (dictionary) of assigned storm events.
  - Forwards queries (`find_event`) around the ring until the event is found.
  - Can leave the ring by notifying the Manager (`leave` command).
  - Shuts down gracefully upon receiving a `teardown` command from the Manager or via `exit`.

---

## Features

1. **CSV Data Loading**: Reads storm event records from a CSV file (e.g., `StormEvents_locations-ftp_v1.0_d2024_c20250317.csv`).  
2. **Ring Maintenance**: The Manager calculates and updates the ring topology whenever a peer joins or leaves.  
3. **Event Distribution**: Each event is hashed by `EVENT_ID` (or a fallback if missing) to decide which peer stores it.  
4. **Query Mechanism**: Peers forward `find_event` messages in a circular fashion until the event is located.  
5. **Dynamic Changes**: Peers can leave the ring gracefully; the Manager updates the ring accordingly.  
6. **UDP Communication**: All communication is done over UDP sockets for simplicity.

---

## Requirements

- **Python 3.7+** (any recent Python 3 version should work)
- A CSV file with a column named `EVENT_ID` (or adapt the code if your CSV format differs)

No additional Python libraries (beyond the standard library) are required.

---

## File Structure

```
.
├── manager.py
├── peer.py
├── StormEvents_locations-ftp_v1.0_d2024_c20250317.csv
├── Socket-Project_Spring2025.pdf
└── README.md  <-- This file
```

- **manager.py**: Implements the Manager process.
- **peer.py**: Implements the Peer process.
- **StormEvents_locations-ftp_v1.0_d2024_c20250317.csv**: Example CSV data (rename if needed).
- **README.md**: Documentation for the project.

---

## Setup & Installation

1. **Clone or Download** this repository onto your local machine.
2. **Verify Python Version**:
   ```bash
   python --version
   ```
   Make sure it’s Python 3.7 or later.
3. **Place the CSV File**:
   - Ensure `StormEvents_locations-ftp_v1.0_d2024_c20250317.csv` is in the same directory as `manager.py`.
   - If you have a different CSV file name, update the `CSV_FILE` variable in `manager.py` accordingly.

No special dependencies are needed besides Python’s standard library.

---

## Usage

### 1. Start the Manager

```bash
python manager.py
```

- The Manager loads the CSV file (if found) and starts listening on `127.0.0.1:5000`.
- You will see a message like `Manager started on 127.0.0.1:5000`.
- The Manager also prints how many events it loaded from the CSV.

### 2. Start One or More Peers

In separate terminals, start each peer with a **unique port**:

```bash
python peer.py 6001
python peer.py 6002
python peer.py 6003
```

- Each peer registers with the Manager and gets assigned a `peer_id`.
- The peer console will prompt you with `Enter command (query <event_id> / leave / exit):`.

### 3. Manager Console Commands

Back in the **Manager** console, you can type:

- **setup**: Sorts peers by ID and sends each a `set_next_peer` command to form a ring.  
- **distribute**: Sends a `store` command for each CSV event to the peer determined by the hash of its `EVENT_ID`.  
- **teardown**: Sends `teardown` to all peers, instructing them to shut down.

---

## Commands

### Manager Console
- **setup**  
  Forms the ring by setting each peer’s `next_peer`.
- **distribute**  
  Distributes CSV events to the peers.
- **teardown**  
  Sends a shutdown command to all peers.

### Peer Console
- **query `<event_id>`**  
  Initiates a search for `<event_id>`. If the peer doesn’t have it, it forwards the query around the ring.  
- **leave**  
  Notifies the Manager that this peer is leaving. The Manager updates the ring accordingly.  
- **exit**  
  Exits the peer process immediately (without notifying the Manager).

---

## Demo Steps

1. **Start the Manager**:
   ```bash
   python manager.py
   ```
   Confirm it loads the CSV events.

2. **Start Peers**:
   ```bash
   python peer.py 6001
   python peer.py 6002
   python peer.py 6003
   ```
   Each peer prints a message with its assigned `peer_id`.

3. **Form the Ring** (Manager console):
   ```bash
   setup
   ```
   The Manager prints the `next_peer` for each peer.

4. **Distribute Events** (Manager console):
   ```bash
   distribute
   ```
   The Manager sends each event to the appropriate peer. Peers print `[Peer X] Stored event ...`; the Manager prints `[Manager] Received store_ack ...`.

5. **Query Events** (Peer console):
   ```bash
   query 1161227
   ```
   If the event is not stored locally, the peer forwards the query. If found, you’ll see `[Peer X] Found event 1161227: {...}`.

6. **Peer Leaving** (Peer console):
   ```bash
   leave
   ```
   This peer notifies the Manager, which removes it and re-runs the ring update.

7. **Teardown** (Manager console):
   ```bash
   teardown
   ```
   All peers shut down gracefully.

---

## License

MIT License 

**Enjoy building and demonstrating your DHT-based Storm Event Tracker!**
