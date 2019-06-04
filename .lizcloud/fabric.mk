#
# Makefile for building/packaging qgis for 3Liz
#

ifndef FABRIC
FABRIC:=$(shell [ -e .fabricrc ] && echo "fab -c .fabricrc" || echo "fab")
endif

VERSION=$(shell ./metadata_key ../metadata.txt version)

main:
	echo "Makefile for packaging infra components: select a task"

PACKAGE=qgis3_atlasprint
FILES = ../filters ../*.py ../metadata.txt ../README.md


build2/atlasprint:
	@rm -rf build2/atlasprint
	@mkdir -p build2/atlasprint

.PHONY: package
package: build2/atlasprint
	@echo "Building package $(PACKAGE)"
	@cp -rLp $(FILES) build2/atlasprint/
	$(FABRIC) package:$(PACKAGE),versiontag=$(VERSION),files=atlasprint,directory=./build2

