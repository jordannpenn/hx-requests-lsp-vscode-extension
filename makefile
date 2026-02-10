.PHONY: install build package clean

# VS Code extensions require Node.js >= 20
# Uses nvm to ensure correct version

SHELL := /bin/bash
NVM_USE := source ~/.nvm/nvm.sh && nvm use 20

install:
	$(NVM_USE) && npm install

build: install
	$(NVM_USE) && npm run compile

package: build
	$(NVM_USE) && npm run package
	@echo ""
	@echo "Built extension: $$(ls -1 *.vsix)"
	@echo "Install in VS Code: Ctrl+Shift+P -> 'Install from VSIX'"

clean:
	rm -rf node_modules out *.vsix
