# Variables
CXX = g++
CXXFLAGS = -std=c++17
CLIENT = client
SERVER = server
CONFIG = config.json
PLOT_SCRIPT = plot.py

# Targets
all: run

build:
	$(CXX) $(CXXFLAGS) -o $(CLIENT) client.cpp
	$(CXX) $(CXXFLAGS) -o $(SERVER) server.cpp

server:
	./$(SERVER)

client:
	./$(CLIENT)

# Run the server and client
run: clean build
	-pkill -9 server || true
	@echo "Running the server..."
	./$(SERVER) &
	sleep 2
	@echo "Running the client..."
	./$(CLIENT)

plot: clean build
	python3 $(PLOT_SCRIPT)

clean:
	rm -f $(CLIENT) $(SERVER)
	rm -f *.o
	rm -f *log.txt
	rm -f output*.txt
	rm -f time*.txt
	rm -f plot*.png

.PHONY: all build run-server run-client run plot clean
