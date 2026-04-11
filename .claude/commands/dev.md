Build the frontend and start the backend server.

Usage: /dev [port]
- port: The port to serve on (default: 3000)

Steps:
1. Build the frontend: `cd frontend && npm run build`
2. Kill any process already listening on the target port
3. Start the backend: `cd /home/workspace/cycling-coach && source venv/bin/activate && uvicorn server.main:app --host 0.0.0.0 --port <port>`
4. Run the server in the background and verify it responds at `/api/version`

Port argument: $ARGUMENTS (default to 3000 if empty)
