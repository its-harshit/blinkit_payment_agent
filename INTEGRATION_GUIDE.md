# Backend-Frontend Integration Guide

This guide explains how to run the unified agent backend with the React frontend.

## Prerequisites

1. **Python Environment**: Ensure you have Python 3.8+ with virtual environment activated
2. **Node.js**: Ensure you have Node.js installed (for frontend)
3. **Dependencies**: Install all required packages

## Setup

### 1. Backend Setup

```bash
# Activate virtual environment (if not already active)
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install Python dependencies (if not already installed)
pip install -r requirements.txt

# Ensure Node.js dependencies for MCP servers are installed
cd mcp_tools
npm install
cd ..
```

### 2. Frontend Setup

```bash
cd frontend
npm install
# This will install react-markdown and remark-gfm for markdown rendering
cd ..
```

## Running the Application

### Step 1: Start the Backend API Server

From the project root directory:

```bash
# Option 1: Using Python module
python -m mcp_tools.api_server

# Option 2: Using uvicorn directly
uvicorn mcp_tools.api_server:app --host 0.0.0.0 --port 8000 --reload
```

The backend will start on `http://localhost:8000`

### Step 2: Start the Frontend

In a new terminal, from the project root:

```bash
cd frontend
npm run dev
```

The frontend will start on `http://localhost:5173` (Vite default port)

## API Endpoints

The backend exposes the following endpoints:

- `POST /api/chat/create` - Create a new chat session
- `GET /api/chat/{chat_id}/messages` - Get message history (placeholder)
- `POST /api/chat/stream` - Stream chat responses (SSE format)
- `POST /api/chat` - Non-streaming chat endpoint

## Frontend Configuration

The frontend is already configured to proxy API requests to `http://localhost:8000` via Vite's proxy (see `frontend/vite.config.js`).

If you need to change the backend URL, you can:
1. Update the proxy target in `frontend/vite.config.js`
2. Or set `VITE_API_BASE_URL` environment variable in frontend

## Features

The integrated system supports:

1. **Chat Interface**: Real-time chat with the unified agent
2. **Streaming Responses**: Server-Sent Events (SSE) for real-time message streaming
3. **Shopping Features**: 
   - Recipe planning and ingredient shopping
   - Product search and cart management
   - Payment processing
4. **NPCI Support**: General NPCI grievance handling

## Testing the Integration

1. Start both backend and frontend
2. Open `http://localhost:5173` in your browser
3. Try these example queries:
   - "Tell me about UPI"
   - "I want to make biryani"
   - "Add all the ingredients to cart"
   - "Show me my cart"
   - "Proceed to payment"

## Troubleshooting

### Backend not starting
- Check if port 8000 is already in use
- Ensure all Python dependencies are installed
- Check that Node.js dependencies in `mcp_tools` are installed

### Frontend not connecting to backend
- Verify backend is running on port 8000
- Check browser console for CORS errors
- Verify Vite proxy configuration in `vite.config.js`

### Streaming not working
- Check browser console for errors
- Verify SSE format in network tab
- Ensure backend is sending proper SSE format (`data: {...}\n\n`)

## Notes

- Each chat session maintains its own agent instance with conversation history
- The agent automatically clears the cart after successful payment
- Tool results (like cart summaries) are displayed in the Dashboard component
