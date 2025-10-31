## makefile for the ietf-knowledge-graphs project

SHELL := /bin/bash
ROOT_DIR := $(PWD)

# ----------------------------------------------------------------------

# Loading (optional) environment variables from file.
# For example, to define PROXY setting :
# PROXY_SRV=xxx.yyy.fr
# PROXY_PORT=8080
-include .env

# ----------------------------------------------------------------------

help:	## Show this help.
	# Get lines with double dash comments and display it
	@fgrep -h "## " $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/## //'

# --- INSTALL ----------------------------------------------------------

install-sparqlworks:
	@echo -e "\033[35m > Install SPARQLWorks  \033[0m - Need Internet access, see https://github.com/danielhmills/sparqlworks"
	@echo -e "PROXY_SRV = ${PROXY_SRV} / PROXY_PORT = ${PROXY_PORT}"
	@PROXY_OPT=$$(if [ -n "${PROXY_SRV}" ] && [ -n "${PROXY_PORT}" ]; then echo --proxy ${PROXY_SRV}:${PROXY_PORT}; else echo ""; fi); \
	curl -L \
	  $$PROXY_OPT \
	  -o ./lib/sparqlworks/sparqlworks.zip \
	  --create-dirs \
	  https://github.com/danielhmills/sparqlworks/archive/refs/tags/0.7.0.zip
	@unzip ./lib/sparqlworks/sparqlworks.zip -d ./lib/sparqlworks/
	@echo -e "\033[35m > Done  \033[0m"

# --- RUN --------------------------------------------------------------

start-rdf4j-docker:	## Start a RDF4J instance on localhost
	@echo -e "\033[35m > Create the rdf4jdb directory structure  \033[0m"
	mkdir -p rdf4jdb/data/
	mkdir -p rdf4jdb/logs/
	mkdir -p rdf4jdb/tomcat-conf/
	@echo -e "\033[35m > Start a RDF4J instance on localhost  \033[0m"
	@docker run\
	  --name rdf4j \
	  --interactive \
	  --rm \
	  -d \
	  --tty \
	  -p 8080:8080 \
	  -e JAVA_OPTS="-Xms1g -Xmx4g" \
	  --volume `pwd`/rdf4jdb/data:/var/rdf4j \
	  --volume `pwd`/rdf4jdb/logs:/usr/local/tomcat/logs \
	  eclipse/rdf4j-workbench:latest
	@echo -e "\033[35m > The RDF4J instance is now available on http://localhost:8080/rdf4j-workbench/ and the server on http://localhost:8080/rdf4j-server/ without authentication \033[0m"
	@echo -e "\033[35m > In case of read/write issue with the local folder structure, ensure write access to the other group, e.g. sudo chmod o+w rdf4jdb -R \033[0m"
	@echo -e "\033[35m > Done  \033[0m"

stop-rdf4j-docker:	## Stop the RDF4J instance on localhost
	@echo -e "\033[35m > Stop the RDF4J instance on localhost  \033[0m"
	@docker container stop rdf4j
	@echo -e "\033[35m > Done  \033[0m"


start-sparqlworks-firefox: ## Open a local SPARQLWorks instance using Firefox
	@echo -e "\033[35m > Stop the RDF4J instance on localhost  \033[0m"
	firefox ./lib/sparqlworks/sparqlworks-0.7.0/sparqlworks.html
	@echo -e "\033[35m > Done  \033[0m"
