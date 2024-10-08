# Variables
CXX = g++
CXXFLAGS = -std=c++17
CLIENT_CSCD = client_cscd
SERVER_CSCD = server_cscd
CLIENT_ALOHA = client_aloha
SERVER_ALOHA = server_aloha
CLIENT_BEB = client_beb
SERVER_BEB = server_beb
CONFIG = config.json
PLOT_SCRIPT = plotx.py

# Targets
all: build run_all

build: build_cscd build_aloha build_beb

build_cscd:
	$(CXX) $(CXXFLAGS) -o $(CLIENT_CSCD) client_cscd.cpp
	$(CXX) $(CXXFLAGS) -o $(SERVER_CSCD) server_cscd.cpp

build_aloha:
	$(CXX) $(CXXFLAGS) -o $(CLIENT_ALOHA) client_aloha.cpp
	$(CXX) $(CXXFLAGS) -o $(SERVER_ALOHA) server_aloha.cpp

build_beb:
	$(CXX) $(CXXFLAGS) -o $(CLIENT_BEB) client_beb.cpp
	$(CXX) $(CXXFLAGS) -o $(SERVER_BEB) server_beb.cpp

# Running the experiments
run_all: run_cscd run_aloha run_beb plot

run_cscd:
	@echo "Running FIFO experiment..."
	-pkill -9 server_cscd || true
	-pkill -9 server_aloha || true
	-pkill -9 server_beb || true
	
	./$(SERVER_CSCD) &
	sleep 2
	./$(CLIENT_CSCD)
	@echo "CSCD experiment completed."

run_aloha:
	@echo "Running ALOHA experiment..."
	-pkill -9 server_aloha || true
	-pkill -9 server_beb || true
	-pkill -9 server_cscd || true

	./$(SERVER_ALOHA) &
	sleep 2
	./$(CLIENT_ALOHA)
	@echo "ALOHA experiment completed."

run_beb:
	@echo "Running BEB experiment..."
	-pkill -9 server_beb || true
	-pkill -9 server_cscd || true
	-pkill -9 server_aloha || true

	./$(SERVER_BEB) &
	sleep 2
	./$(CLIENT_BEB)
	@echo "BEB experiment completed."

plot: build
	python3 $(PLOT_SCRIPT)

clean:
	rm -f $(CLIENT) $(SERVER) $(CLIENT_ALOHA) $(SERVER_ALOHA) $(CLIENT_BEB) $(SERVER_BEB)
	rm -f *.o
	rm -f *log.txt
	rm -f time*.txt
	rm -f output*.txt

.PHONY: all build run_all run_fifo run_aloha run_beb plot clean
