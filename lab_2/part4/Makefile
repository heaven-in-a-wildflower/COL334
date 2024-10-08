# Variables
CXX = g++
CXXFLAGS = -std=c++17
CLIENT = client
CLIENT_ROGUE = client_rogue
SERVER = server
SERVER_RR = server_rr
CONFIG = config.json
PLOT_SCRIPT = plot.py
PLOT_ROGUE_SCRIPT = plot_rogue.py
JFI_SCRIPT = jain.py

# Targets
all: run

build:
	$(CXX) $(CXXFLAGS) -o $(CLIENT) client.cpp
	$(CXX) $(CXXFLAGS) -o $(CLIENT_ROGUE) client_rogue.cpp
	$(CXX) $(CXXFLAGS) -o $(SERVER) server.cpp
	$(CXX) $(CXXFLAGS) -o $(SERVER_RR) server_rr.cpp

server-fifo: build
	./$(SERVER)

client-fifo: build
	./$(CLIENT)

server-rr: build
	./$(SERVER)

client-rr: build
	./$(CLIENT)

client-rogue: build
	./$(CLIENT_ROGUE)

run-fifo: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	./$(SERVER) &
	sleep 2
	./$(CLIENT)
	-pkill -9 server || true

run-rr: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	./$(SERVER_RR) &
	sleep 2
	./$(CLIENT)
	-pkill -9 server_rr || true

run-fifo-rogue: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	./$(SERVER) &
	sleep 2
	./$(CLIENT_ROGUE)
	-pkill -9 server || true

run-rr-rogue: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	./$(SERVER_RR) &
	sleep 2
	./$(CLIENT_ROGUE)
	-pkill -9 server_rr || true

run: run-fifo run-rr

fairness: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	@echo "Running the server..."
	./$(SERVER) &
	sleep 2
	@echo "Running the client..."
	./$(CLIENT_ROGUE)
	sleep 2
	python3 $(JFI_SCRIPT)
	-pkill -9 server || true
	-pkill -9 server_rr || true
	@echo "Running the server..."
	./$(SERVER_RR) &
	sleep 2
	@echo "Running the client..."
	./$(CLIENT_ROGUE)
	sleep 2
	python3 $(JFI_SCRIPT)

# Run the server and client
rogue: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	@echo "Running the server..."
	./$(SERVER) &
	sleep 2
	@echo "Running the client..."
	./$(CLIENT_ROGUE)
	sleep 2
	python3 $(PLOT_SCRIPT)

rogue_rr: clean build
	-pkill -9 server || true
	-pkill -9 server_rr || true
	@echo "Running the server..."
	./$(SERVER_RR) &
	sleep 2
	@echo "Running the client..."
	./$(CLIENT_ROGUE)
	sleep 2
	python3 $(PLOT_SCRIPT)

jain: clean build 
	python3 $(JFI_SCRIPT)

plot: clean build
	python3 $(PLOT_SCRIPT)

plot-rogue: clean build
	python3 $(PLOT_ROGUE_SCRIPT)

clean:
	rm -f $(CLIENT) $(SERVER)
	rm -f *.o
	rm -f *log.txt
	rm -f output*.txt
	rm -f time*.txt
	rm -f plot*.png

.PHONY: all build run-server run-client run plot clean
