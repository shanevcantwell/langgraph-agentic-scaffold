const express = require('express');
const path = require('path');
const cors = require('cors');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = process.env.PORT || 3000;
const API_URL = process.env.API_URL || 'http://app:8000';

app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

// Proxy API requests to the Python backend
app.use('/v1', createProxyMiddleware({
    target: API_URL,
    changeOrigin: true,
    ws: true, // Support WebSocket/SSE if needed
    onProxyRes: function (proxyRes, req, res) {
        // Ensure SSE headers are passed correctly
        if (req.path.includes('/stream')) {
            proxyRes.headers['Cache-Control'] = 'no-cache';
            proxyRes.headers['Connection'] = 'keep-alive';
        }
    }
}));

app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
    console.log(`🖥️  V.E.G.A.S. Terminal running on port ${PORT}`);
    console.log(`🔗 Connected to API at ${API_URL}`);
});
