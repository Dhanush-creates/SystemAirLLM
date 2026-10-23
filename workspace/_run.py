import socket
try:
    socket.create_connection(("1.1.1.1", 443), timeout=5)
    print("REACHED the internet")
except OSError as e:
    print("BLOCKED:", e)
