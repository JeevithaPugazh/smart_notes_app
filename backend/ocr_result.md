# Node.js
## Introduction to Node.js
Node.js is a **runtime environment** that allows **JavaScript (JS)** to be executed outside of a **browser**. It runs on the **V8 Engine**, which is a **JavaScript engine** developed by Google for the Google Chrome browser.

## Key Features of Node.js
* **Single-threaded**: Node.js operates on a single thread, which makes it efficient for handling multiple requests concurrently.
* **Asynchronous**: Node.js uses an asynchronous, **non-blocking I/O model**, which enables it to handle a large number of connections simultaneously without performance degradation.
* **Non-blocking**: This model allows Node.js to perform other tasks while waiting for I/O operations to complete.

## Node.js vs. Browser Environment
* Node.js and browser environments both use the **V8 Engine** to execute JavaScript.
* However, Node.js does not provide access to **Browser Object Model (BOM) methods**, which are used for interacting with the browser.

## Creating a Node.js Server
The following steps outline the process of creating a basic Node.js server:

* Require the **http module**: The first step is to include the http module, which provides functionality for creating an HTTP server.
* Create a server with a callback function: The server is created with a callback function that allows us to read **request properties**.
* Set **header**, **content**, and other properties: Configure the server response with the appropriate headers and content.
* Listen on a port: Start the server and listen on a specified port (e.g., port 3000).
* Example:
```javascript
// Require the http module
const http = require('http');

// Create a server with a callback function
const server = http.createServer((req, res) => {
  // Set header, content, and more
  res.writeHead(200, {'Content-Type': 'text/plain'});
  res.end('Hello World\n');
});

// Listen on port 3000
server.listen(3000, () => {
  console.log('Server running');
});
```
## Initialization
To initialize a new Node.js project, run the command:
```bash
npm init -y
```