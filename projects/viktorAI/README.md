# ViktorAI - AI Quiz Tutoring System

AI quiz tutoring system that gives you a quiz tailored to what you have been learning. After you complete the quiz it gives you points you need to work on, things that you have missed/forgotten and what you're good at. Finally it shows you a chart of your progress over time.

## Prerequisites
- Node.js installed
- Docker installed (for MongoDB)

## Quick Start Guide

### 1. Start MongoDB Database
```powershell
# Start MongoDB using Docker (easiest option)
docker run -d --name mongodb -p 27017:27017 mongo:latest

# Verify it's running
docker ps
```

### 2. Backend Setup

Navigate to the server directory:
```powershell
cd server
```

Install dependencies:
```powershell
npm install
```

The `.env` file is already configured with:
```
PORT=8081
MONGODB_URI=mongodb://localhost:27017/test
SALT=10
JWT_ACCESS_SECRET=9a5e595e16623ee4d0ad83b07f09fe74debfa47e02233c51fbd03a3a23ca3770
JWT_REFRESH_SECRET=wpAf+dAYWUnD/5MCmkGavQS9o/QAux3mVcRCppl8vxo-
GEMINI_API_KEY=AIzaSyAyzDEFfYOlynNkN7gRNKdJuzYh65aug_0
CHISEL_URL=http://localhost:8080
ACCESS_TOKEN=kJ9mP2vL8xQ5nR3tY7wZ6cB4dF2gH8jK9lM3nP5qR7sT2uV6wX8yZ9aB3cD5eF7gH2iJ4kL6mN8oP9qR2sT4uV6wX8yZ1aB3cD5eF7gH9iJ2kL
```

Start the development server:
```powershell
npm run dev
```

### 3. Frontend Setup

Navigate to the client directory (in a new terminal):
```powershell
cd client
```

Install dependencies:
```powershell
npm install
```

Start the development server:
```powershell
npm run dev
```

## Access Points
- **Server API**: http://localhost:8081
- **Client App**: http://localhost:5173 (Vite default)

## Troubleshooting

### MongoDB Connection Issues
If you encounter `ECONNREFUSED` errors:
```powershell
# Stop and remove existing container
docker stop mongodb
docker rm mongodb

# Start fresh container
docker run -d --name mongodb -p 27017:27017 mongo:latest
```

### Alternative: MongoDB Atlas (Cloud)
If Docker doesn't work:
1. Create free account at [MongoDB Atlas](https://www.mongodb.com/atlas)
2. Create cluster and get connection string
3. Update `MONGODB_URI` in `.env` with Atlas connection string

### Port Conflicts
If ports are in use:
- Change `PORT=8081` in `.env` to another port
- Update client API configuration accordingly

### Features

- Creates quizzes for students
- Track student progress and quiz attempts
- Provide personalized feedback based on quiz performance
- Multiple choice question generation and assessment 
