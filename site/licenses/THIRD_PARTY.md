# Browser demo dependencies

The static demo bundles unmodified Pyodide 0.27.7 assets at build time. Pyodide runs the publicly available application business rules locally in the browser. It does not connect to the production API.

- Pyodide 0.27.7, Mozilla Public License 2.0. The full license is in `PYODIDE-LICENSE.txt`. Source: https://github.com/pyodide/pyodide/tree/0.27.7
- Pyodide includes CPython and its standard library under the Python Software Foundation license and bundled component notices. Distribution/source: https://www.python.org/downloads/source/ and https://github.com/pyodide/pyodide/tree/0.27.7
- python-barcode 0.16.1, MIT license. License: `PYTHON-BARCODE-LICENSE.txt`. Source: https://github.com/WhyNotHugo/python-barcode

Runtime files are downloaded from the versioned Pyodide distribution and checked against the SHA-256 values in `demo/pyodide-assets.json`. They are served from the same Pages origin as the application. The demo publishes only fictional seeded records; no server secrets, production database, or login credentials are included.
