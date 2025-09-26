const express = require('express');
const { chromium } = require('playwright');

/**
 * InteractiveGUIDemo provides an interactive GUI dashboard
 * demonstrating UI interactions via browser automation.
 */
class InteractiveGUIDemo {
  constructor() {
    this.app = express();
    this.dashboardPort = 3003;
    this.browser = null;
    this.page = null;
    this.apiCalls = [];
    this.currentStep = 0;
    this.demoSteps = [
      { action: 'navigate', target: 'Home', description: '🏠 Navigate to Home page' },
      { action: 'navigate', target: 'Chat', description: '💬 Click on Chat navigation' },
      { action: 'navigate', target: 'Projects', description: '📁 Click on Projects navigation' },
      { action: 'navigate', target: 'Notes', description: '📝 Click on Notes navigation' },
      { action: 'navigate', target: 'Files', description: '📂 Click on Files navigation' },
      { action: 'refresh', description: '🔄 Refresh page to trigger API calls' },
    ];
  }

  /**
   * Starts the interactive dashboard server and configures routes
   * for serving the dashboard UI, API data endpoints, and demo controls.
   * @returns {Promise<void>}
   */
  async startDashboard() {
    this.app.use(express.json());

    // Serve the dashboard HTML
    this.app.get('/', (req, res) => {
      res.send(this.generateInteractiveDashboard());
    });

    // Get API call data
    this.app.get('/api/calls', (req, res) => {
      res.json({
        calls: this.apiCalls,
        totalCalls: this.apiCalls.length,
        currentStep: this.currentStep,
        totalSteps: this.demoSteps.length,
      });
    });

    // Manual trigger endpoint
    this.app.post('/api/demo/next', async (req, res) => {
      try {
        if (!this.browser || !this.page) {
          // Initialize browser if not already done
          await this.initializeBrowser();
        }
        const result = await this.performNextDemoStep();
        res.json(result);
      } catch (error) {
        res.status(500).json({
          success: false,
          error: error.message,
        });
      }
    });

    // Start demo endpoint
    this.app.post('/api/demo/start', async (req, res) => {
      try {
        await this.initializeBrowser();
        res.json({ success: true, message: 'Demo browser initialized' });
      } catch (error) {
        res.status(500).json({
          success: false,
          error: error.message,
        });
      }
    });

    this.app.listen(this.dashboardPort, () => {
      console.log(`🎮 Interactive GUI Demo Dashboard: http://localhost:${this.dashboardPort}`);
    });
  }
}

  /**
   * Initializes the browser and page if not already initialized.
   * @returns {Promise<void>} Resolves when browser and page are initialized.
   */
  async initializeBrowser() {
    if (this.browser && this.page) {
      return; // Already initialized
    }

    console.log('🌐 Initializing browser...');
    this.browser = await chromium.launch({ headless: false });

    const context = await this.browser.newContext();
    this.page = await context.newPage();

    this.setupNetworkMonitoring();

    // Navigate to DinoAir frontend
    await this.page.goto('http://localhost:5173');
    console.log('✅ Browser ready!');
  }

  setupNetworkMonitoring() {
    // Monitor network requests
    this.page.on('request', request => {
      const url = request.url();
      if (url.includes('localhost') || url.includes('127.0.0.1')) {
        const call = {
          type: 'request',
          method: request.method(),
          path: new URL(url).pathname,
          timestamp: new Date().toISOString(),
        };
        this.apiCalls.push(call);
        this.logCall('📤 REQUEST', call);
      }
    });

    // Monitor network responses
    this.page.on('response', response => {
      const url = response.url();
      if (url.includes('localhost') || url.includes('127.0.0.1')) {
        const call = {
          type: 'response',
          method: response.request().method(),
          path: new URL(url).pathname,
          status: response.status(),
          statusText: response.statusText(),
          timestamp: new Date().toISOString(),
        };
        this.apiCalls.push(call);
        this.logCall('📥 RESPONSE', call);
      }
    });

    // Monitor network failures
    this.page.on('requestfailed', request => {
      const url = request.url();
      if (url.includes('localhost') || url.includes('127.0.0.1')) {
        const call = {
          type: 'failed',
          method: request.method(),
          path: new URL(url).pathname,
          error: request.failure().errorText,
          timestamp: new Date().toISOString(),
        };
        this.apiCalls.push(call);
        this.logCall('❌ FAILED', call);
      }
    });
  }

    /**
     * Performs the next step of the interactive GUI demo.
     * Throws an error if the browser is not initialized.
     * Initializes currentStep to 0 if not set, loops demo steps, and executes GUI actions.
     * @returns {Promise<{success: boolean, step: number, description?: string, nextStep?: string, error?: string}>} Result of performing the demo step.
     */
    async performNextDemoStep() {
      if (!this.page) {
        throw new Error('Browser not initialized. Please start the demo first.');
      }

      if (!this.currentStep) {
        this.currentStep = 0;
      }

      if (this.currentStep >= this.demoSteps.length) {
        console.log('🎉 All demo steps completed! Restarting from the beginning...');
        this.currentStep = 0;
      }

      const step = this.demoSteps[this.currentStep];
      console.log(
        `
  🎬 Manual Step ${this.currentStep + 1}/${this.demoSteps.length}: ${step.description}`
      );

      try {
        await this.performGUIAction(step);
        this.currentStep++;
        return {
          success: true,
          step: this.currentStep,
          description: step.description,
          nextStep:
            this.currentStep < this.demoSteps.length
              ? this.demoSteps[this.currentStep].description
              : 'Demo completed - will restart',
        };
      } catch (error) {
        console.error(`❌ Error in manual step ${this.currentStep + 1}:`, error.message);
        return {
          success: false,
          error: error.message,
          step: this.currentStep + 1,
        };
      }
    }

  /**
   * Performs a GUI action based on the given step.
   * @param {Object} step - The step object containing action and target.
   * @param {string} step.action - The type of action to perform (e.g., 'navigate', 'refresh').
   * @param {string} [step.target] - The target for navigation actions.
   * @returns {Promise<void>} A promise that resolves when the action is complete.
   */
  async performGUIAction(step) {
    switch (step.action) {
      case 'navigate':
        if (step.target === 'Home') {
          await this.page.click('a[href="/"]');
        } else {
          await this.clickNavigation(step.target);
        }
        break;
      case 'refresh':
        await this.page.reload();
        break;
      default:
        console.log(`⚠️ Unknown action: ${step.action}`);
    }
  }

  async clickNavigation(target) {
    const navSelectors = [
      `nav a[href*="${target.toLowerCase()}"]`,
      `[data-testid*="${target.toLowerCase()}"]`,
      `text="${target}"`,
      `text=/.*${target}.*/i`,
    ];

    for (const selector of navSelectors) {
      try {
        const element = this.page.locator(selector).first();
        if (await element.isVisible({ timeout: 2000 })) {
          await element.click();
          console.log(`✅ Clicked ${target} navigation`);
          return;
        }
      } catch (error) {
        // Try next selector
      }
    }
    console.log(`⚠️ Could not find ${target} navigation element`);
  }

  /**
   * Logs the call details to the console with a timestamp.
   * @param {string} type - The type of the call.
   * @param {Object} call - The call details including method, path, timestamp, and status.
   * @returns {void}
   */
  logCall(type, call) {
    const timestamp = new Date(call.timestamp).toLocaleTimeString();
    console.log(`[${timestamp}] ${type} - ${call.method} ${call.path}`);

    if (call.status) {
      const emoji = call.status >= 200 && call.status < 300 ? '✅' : '❌';
  /**
   * Logs the status and status text for a call and any errors to the console.
   * @param {Object} call - The call object containing status, statusText, and error information.
   * @returns {void}
   */
  logCall(call) {
      console.log(`  ${emoji} ${call.status} ${call.statusText}`);
    }

    if (call.error) {
      console.log(`  ❌ ${call.error}`);
    }
  }

  /**
   * Generates an interactive HTML dashboard for the GUI demo.
   * @returns {string} HTML string of the interactive demo dashboard.
   */
  generateInteractiveDashboard() {
    return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎮 Interactive GUI Demo Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }

        .dashboard {
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            padding: 30px;
            backdrop-filter: blur(10px);
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e6ed;
        }

        .header h1 {
            font-size: 2.5em;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }

        .controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
`;
  }
            gap: 20px;
            margin-bottom: 30px;
        }

        .control-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            color: white;
            box-shadow: 0 10px 20px rgba(240, 147, 251, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .control-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(240, 147, 251, 0.4);
        }

        .control-btn {
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
            margin-top: 10px;
        }

        .control-btn:hover {
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
            transform: scale(1.05);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 15px;
            padding: 25px;
            color: white;
            text-align: center;
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }

        .stat-number {
            font-size: 3em;
            font-weight: bold;
            margin-bottom: 10px;
        }

        .stat-label {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .calls-container {
            background: #f8fafc;
            border-radius: 15px;
            padding: 25px;
            max-height: 500px;
            overflow-y: auto;
        }

        .calls-header {
            font-size: 1.5em;
            font-weight: bold;
            margin-bottom: 20px;
            color: #667eea;
        }

        .call-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            margin-bottom: 8px;
            background: white;
            border-radius: 10px;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            transition: transform 0.2s ease;
        }

        .call-item:hover {
            transform: translateX(5px);
        }

        .call-method {
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 5px;
            color: white;
            font-size: 0.8em;
        }

        .method-GET { background: #10b981; }
        .method-POST { background: #3b82f6; }
        .method-PUT { background: #f59e0b; }
        .method-DELETE { background: #ef4444; }

        .call-path {
            flex-grow: 1;
            margin: 0 15px;
            font-family: 'Courier New', monospace;
        }

        .call-status {
            font-weight: bold;
        }

        .status-success { color: #10b981; }
        .status-error { color: #ef4444; }

        .demo-progress {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            color: white;
        }

        .progress-bar {
            background: rgba(255, 255, 255, 0.3);
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin-top: 10px;
        }

        .progress-fill {
            background: white;
            height: 100%;
            transition: width 0.3s ease;
            border-radius: 10px;
        }

        .no-calls {
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>🎮 Interactive GUI Demo Dashboard</h1>
            <p>Monitor and control automated DinoAir frontend interactions</p>
        </div>

        <div class="controls">
            <div class="control-card">
                <h3>🚀 Initialize Demo</h3>
                <p>Start the browser and connect to DinoAir</p>
                <button class="control-btn" onclick="startDemo()">Start Demo</button>
            </div>

            <div class="control-card">
                <h3>▶️ Next Step</h3>
                <p>Trigger the next GUI interaction manually</p>
                <button class="control-btn" onclick="triggerNextStep()">Next Step</button>
            </div>
        </div>

        <div id="demo-progress" class="demo-progress" style="display: none;">
            <h3>📊 Demo Progress</h3>
            <div>Step <span id="current-step">0</span> of <span id="total-steps">6</span></div>
            <div class="progress-bar">
                <div id="progress-fill" class="progress-fill" style="width: 0%;"></div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div id="total-calls" class="stat-number">0</div>
                <div class="stat-label">Total API Calls</div>
            </div>

            <div class="stat-card">
                <div id="current-step-display" class="stat-number">0</div>
                <div class="stat-label">Current Step</div>
            </div>
        </div>

        <div class="calls-container">
            <div class="calls-header">🔗 Live API Calls</div>
            <div id="calls-list">
                <div class="no-calls">🎯 Initialize the demo to start monitoring API calls</div>
            </div>
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/calls')
                .then(response => response.json())
                .then(data => {
                    updateStats(data);
                    updateCallsList(data.calls);
                    updateProgress(data);
                })
                .catch(error => console.error('Error:', error));
        }

        function updateStats(data) {
            document.getElementById('total-calls').textContent = data.totalCalls;
            document.getElementById('current-step-display').textContent = data.currentStep;
            document.getElementById('current-step').textContent = data.currentStep;
            document.getElementById('total-steps').textContent = data.totalSteps;
        }

        function updateProgress(data) {
            const progressContainer = document.getElementById('demo-progress');
            if (data.currentStep > 0) {
                progressContainer.style.display = 'block';
                const percentage = (data.currentStep / data.totalSteps) * 100;
                document.getElementById('progress-fill').style.width = percentage + '%';
            }
        }

        function updateCallsList(calls) {
            const callsList = document.getElementById('calls-list');

            if (calls.length === 0) {
                callsList.innerHTML = '<div class="no-calls">🎯 Initialize the demo to start monitoring API calls</div>';
                return;
            }

            const recentCalls = calls.slice(-20).reverse();
            callsList.innerHTML = recentCalls.map(call => {
                const statusClass = call.status && call.status >= 200 && call.status < 300 ? 'status-success' : 'status-error';
                const methodClass = 'method-' + call.method;
                const icon = getPathIcon(call.path);

                return \`
                    <div class="call-item">
                        <span class="call-method \${methodClass}">\${call.method}</span>
                        <span class="call-path">\${icon} \${call.path}</span>
                        <span class="call-status \${statusClass}">
                            \${call.status ? call.status + ' ' + call.statusText : call.error || 'Pending'}
                        </span>
                    </div>
                \`;
            }).join('');
        }

        function getPathIcon(path) {
            if (path.includes('health')) return '💓';
            if (path.includes('search')) return '🔎';
            if (path.includes('api')) return '🔗';
            if (path.includes('assets')) return '📦';
            if (path.includes('src')) return '📄';
            return '🌐';
        }

        function startDemo() {
            fetch('/api/demo/start', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        console.log('Demo started successfully');
                        updateDashboard();
                    } else {
                        console.error('Error starting demo:', data.error);
                    }
                })
                .catch(error => {
                    console.error('Error starting demo:', error);
                });
        }

        function triggerNextStep() {
            fetch('/api/demo/next', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        console.log('Triggered step:', data.step);
                        updateDashboard();
                    } else {
                        console.error('Error triggering step:', data.error);
                    }
                })
                .catch(error => {
                    console.error('Error triggering step:', error);
                });
        }

        // Update every second
        setInterval(updateDashboard, 1000);
        updateDashboard();
    </script>
</body>
</html>
    `;
  }

  /**
   * Stops the interactive demo by logging a stop message and closing the browser if open.
   *
   * @returns {Promise<void>} A promise that resolves once the browser is closed.
   */
  async stop() {
    console.log('🛑 Interactive demo stopped');
    if (this.browser) {
      await this.browser.close();
    }
  }
}

// Handle graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n🛑 Shutting down...');
  if (global.demoInstance) {
    await global.demoInstance.stop();
  }
  process.exit(0);
});

// Start the demo
const demo = new InteractiveGUIDemo();
global.demoInstance = demo;
demo.startDashboard();
