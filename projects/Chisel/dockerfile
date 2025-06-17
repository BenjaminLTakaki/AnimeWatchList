# syntax=docker/dockerfile:1
FROM golang:1.24-alpine

WORKDIR /app

# Cache go.mod and go.sum before full source copy
COPY go.mod ./
RUN go mod download

# Copy rest of source
COPY . .

# Build the Go app
RUN go build -o main .

EXPOSE 8080

ENV PORT=8080
# Run the app
CMD ["./main"]
