/**
 * DinoAir Express Server with Datadog Metrics
 * Example server showing how to integrate hot-shots metrics collection
 */

const express = require('express');
const { dogstatsd, createMetricsMiddleware, trackBusinessMetrics } = require('./metrics-example');

const app = express();
const PORT = process.env.PORT || 3000;

// Add metrics middleware
app.use(createMetricsMiddleware());

// Middleware for JSON parsing
app.use(express.json());

// Routes with custom metrics
app.get('/health', (req, res) => {
  // Track health check
  dogstatsd.increment('health_checks.total');

  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    service: 'dinoair-nodejs',
    version: '1.0.0',
  });
});

app.get('/api/users', (req, res) => {
  // Simulate database query with timing
  const startTime = Date.now();

  // Simulate work
  setTimeout(
    () => {
      const queryTime = Date.now() - startTime;
      dogstatsd.timing('database.query', queryTime, ['table:users']);

      // Track business metric
      dogstatsd.gauge('api.users.count', 42);

      res.json({
        users: [
          { id: 1, name: 'John Doe', active: true },
          { id: 2, name: 'Jane Smith', active: true },
        ],
        count: 42,
        query_time_ms: queryTime,
      });
    },
    Math.random() * 100 + 50
  ); // 50-150ms delay
});

app.post('/api/events', (req, res) => {
  const { type } = req.body;

  // Track event creation
  dogstatsd.increment('events.created', 1, [`event_type:${type || 'unknown'}`]);

  // Simulate processing
  const success = Math.random() > 0.1; // 90% success rate

  if (success) {
    res.status(201).json({
      message: 'Event created successfully',
      event_id: Math.random().toString(36).substr(2, 9),
    });
  } else {
    dogstatsd.increment('events.creation_failed', 1);
    res.status(500).json({
      error: 'Failed to create event',
    });
  }
});

app.get('/metrics/demo', (req, res) => {
  // Trigger business metrics collection
  trackBusinessMetrics();

  res.json({
    message: 'Business metrics generated',
    timestamp: new Date().toISOString(),
  });
});

// Error handling middleware with metrics
app.use((err, req, res, _next) => {
  dogstatsd.increment('errors.unhandled', 1, [
    `error_type:${err.name || 'unknown'}`,
    `route:${req.path}`,
  ]);

  console.error('Unhandled error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// 404 handler with metrics
app.use('*', (req, res) => {
  dogstatsd.increment('http.404', 1, [`path:${req.path}`]);
  res.status(404).json({ error: 'Not found' });
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down server...');
  dogstatsd.close(() => {
    console.log('📤 StatsD client closed');
    process.exitCode = 0;
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 DinoAir Node.js server running on port ${PORT}`);
  console.log('📊 Metrics collection active with hot-shots');
  console.log('🔗 Test endpoints:');
  console.log(`   GET  http://localhost:${PORT}/health`);
  console.log(`   GET  http://localhost:${PORT}/api/users`);
  console.log(`   POST http://localhost:${PORT}/api/events`);
  console.log(`   GET  http://localhost:${PORT}/metrics/demo`);

  // Track server startup
  dogstatsd.increment('server.startup', 1);
  dogstatsd.gauge('server.port', PORT);
});

module.exports = app;
