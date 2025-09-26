/**
 * DinoAir Node.js Metrics Collection Example
 * Using hot-shots library for Datadog StatsD metrics
 */

const StatsD = require('hot-shots');

// Initialize the StatsD client
const dogstatsd = new StatsD({
  host: 'localhost',
  port: 8125,
  prefix: 'dinoair.nodejs.',
  globalTags: ['service:dinoair-node', 'environment:prod', 'version:1.0.0'],
});

/**
 * Business Metrics Examples
 */
function trackBusinessMetrics() {
  console.log('📊 Tracking Node.js Business Metrics...');

  // 1. Page view counter (equivalent to Python example)
  const pages = ['dashboard', 'settings', 'profile', 'help'];
  const page = pages[Math.floor(Math.random() * pages.length)];

  dogstatsd.increment('page.views', 1, [`page:${page}`]);
  console.log(`  📄 Page view tracked: ${page}`);

  // 2. User activity gauge
  const activeUsers = Math.floor(Math.random() * 100) + 50;
  dogstatsd.gauge('users.active', activeUsers);
  console.log(`  👥 Active users: ${activeUsers}`);

  // 3. Response time histogram
  const responseTime = Math.random() * 500 + 50; // 50-550ms
  dogstatsd.histogram('api.response_time', responseTime, ['endpoint:/api/data']);
  console.log(`  ⚡ Response time: ${responseTime.toFixed(2)}ms`);

  // 4. Feature usage counter
  const features = ['search', 'export', 'share', 'print'];
  features.forEach(feature => {
    const usage = Math.floor(Math.random() * 20) + 1;
    dogstatsd.increment('feature.usage', usage, [`feature:${feature}`]);
    console.log(`  🔧 Feature usage - ${feature}: ${usage}`);
  });

  // 5. Error rate tracking
  const isError = Math.random() < 0.1; // 10% error rate
  if (isError) {
    dogstatsd.increment('errors.total', 1, ['type:server_error']);
    console.log('  ❌ Error tracked');
  } else {
    dogstatsd.increment('requests.successful', 1);
    console.log('  ✅ Successful request tracked');
  }
}

/**
 * Performance Metrics Examples
 */
function trackPerformanceMetrics() {
  console.log('\n⚡ Tracking Performance Metrics...');

  // 1. Database query timing
  const queryTime = Math.random() * 200 + 10; // 10-210ms
  dogstatsd.timing('database.query', queryTime, ['table:users']);
  console.log(`  🗄️  Database query time: ${queryTime.toFixed(2)}ms`);

  // 2. Memory usage gauge
  const memoryUsage = process.memoryUsage();
  dogstatsd.gauge('system.memory.used', memoryUsage.heapUsed);
  dogstatsd.gauge('system.memory.total', memoryUsage.heapTotal);
  console.log(`  💾 Memory usage: ${(memoryUsage.heapUsed / 1024 / 1024).toFixed(2)}MB`);

  // 3. Cache hit rate
  const cacheHitRate = Math.random() * 0.3 + 0.7; // 70-100%
  dogstatsd.gauge('cache.hit_rate', cacheHitRate * 100, ['cache:redis']);
  console.log(`  🎯 Cache hit rate: ${(cacheHitRate * 100).toFixed(1)}%`);

  // 4. Queue length
  const queueLength = Math.floor(Math.random() * 50);
  dogstatsd.gauge('queue.length', queueLength, ['queue:processing']);
  console.log(`  📋 Queue length: ${queueLength}`);
}

/**
 * Security Metrics Examples
 */
function trackSecurityMetrics() {
  console.log('\n🔒 Tracking Security Metrics...');

  // 1. Authentication attempts
  const authSuccess = Math.random() > 0.2; // 80% success rate
  if (authSuccess) {
    dogstatsd.increment('auth.success', 1);
    console.log('  ✅ Successful authentication');
  } else {
    dogstatsd.increment('auth.failure', 1, ['reason:invalid_password']);
    console.log('  ❌ Failed authentication');
  }

  // 2. Rate limiting
  const isRateLimited = Math.random() < 0.05; // 5% rate limited
  if (isRateLimited) {
    dogstatsd.increment('security.rate_limited', 1, ['endpoint:/api/data']);
    console.log('  🚫 Rate limit triggered');
  }

  // 3. Security events
  const securityEvents = ['sql_injection_attempt', 'xss_attempt', 'brute_force'];
  if (Math.random() < 0.1) {
    // 10% chance of security event
    const event = securityEvents[Math.floor(Math.random() * securityEvents.length)];
    dogstatsd.increment('security.events', 1, [`event_type:${event}`, 'severity:high']);
    console.log(`  🚨 Security event: ${event}`);
  }
}

/**
 * Custom Timer Example (like Python's @timed decorator)
 */
function timedFunction(name, fn) {
  return function (...args) {
    const startTime = Date.now();
    const result = fn.apply(this, args);
    const duration = Date.now() - startTime;

    dogstatsd.timing('function.execution_time', duration, [`function:${name}`]);
    console.log(`  ⏱️  Function ${name} executed in ${duration}ms`);

    return result;
  };
}

/**
 * Example business function with timing
 */
const processOrder = timedFunction('processOrder', function (orderId) {
  // Simulate processing time
  const processingTime = Math.random() * 1000 + 500;
  const startTime = Date.now();
  while (Date.now() - startTime < processingTime) {
    // Busy wait to simulate processing
  }
  return `Order ${orderId} processed`;
});

/**
 * Main demonstration function
 */
function demonstrateNodejsMetrics() {
  console.log('🎯 DinoAir Node.js Metrics Demonstration with hot-shots');
  console.log('='.repeat(60));

  // Track various metrics
  trackBusinessMetrics();
  trackPerformanceMetrics();
  trackSecurityMetrics();

  // Demonstrate timed function
  console.log('\n⏱️  Demonstrating timed function...');
  processOrder('ORD-12345');

  console.log('\n✅ Node.js metrics demonstration complete!');
  console.log('🔍 Check your Datadog dashboard for metrics with prefix: dinoair.nodejs.*');

  // Flush metrics and exit
  dogstatsd.close(error => {
    if (error) {
      console.error('Error closing StatsD client:', error);
    } else {
      console.log('📤 StatsD client closed successfully');
    }
    process.exitCode = 0;
  });
}

/**
 * Express middleware for automatic metrics collection
 */
function createMetricsMiddleware() {
  return (req, res, next) => {
    const startTime = Date.now();

    // Track request count
    dogstatsd.increment('http.requests', 1, [
      `method:${req.method}`,
      `route:${req.route?.path || req.path}`,
    ]);

    // Override res.end to capture response metrics
    const originalEnd = res.end;
    res.end = function (...args) {
      const duration = Date.now() - startTime;

      // Track response time
      dogstatsd.timing('http.response_time', duration, [
        `method:${req.method}`,
        `route:${req.route?.path || req.path}`,
        `status_code:${res.statusCode}`,
      ]);

      // Track response by status code
      const statusClass = Math.floor(res.statusCode / 100);
      dogstatsd.increment('http.responses', 1, [
        `method:${req.method}`,
        `route:${req.route?.path || req.path}`,
        `status_code:${res.statusCode}`,
        `status_class:${statusClass}xx`,
      ]);

      originalEnd.apply(this, args);
    };

    next();
  };
}

// Export for use in other modules
module.exports = {
  dogstatsd,
  trackBusinessMetrics,
  trackPerformanceMetrics,
  trackSecurityMetrics,
  timedFunction,
  createMetricsMiddleware,
};

// Run demonstration if this file is executed directly
if (require.main === module) {
  demonstrateNodejsMetrics();
}
