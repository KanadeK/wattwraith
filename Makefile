.PHONY: verify demo package release-check

verify:
	python scripts/verify.py

demo:
	python scripts/demo.py

package:
	python scripts/package_release.py

release-check:
	python scripts/release_check.py
