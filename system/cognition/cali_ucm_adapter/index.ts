type TestCognitionInput = Record<string, unknown> | undefined;
type IntegratedCore4RuntimeConstructor = new () => {
  stepWithTransport(input?: unknown): unknown;
};

interface CaliUcmRuntimeModule {
  IntegratedCore4Runtime: IntegratedCore4RuntimeConstructor;
}

export interface CaliUcmAdapterConfig {
  enabled?: boolean;
  env?: Record<string, string | undefined>;
}

export interface CaliUcmDisabledResult {
  routed: false;
  reason: "CALI_UCM_DISABLED";
}

export interface CaliUcmRoutedResult {
  routed: true;
  source: "CALI_UCM";
  result: unknown;
}

export type CaliUcmAdapterResult = CaliUcmDisabledResult | CaliUcmRoutedResult;

function flagEnabled(env: Record<string, string | undefined> = process.env || {}): boolean {
  return String(env.CALI_UCM_ENABLED || "").trim().toLowerCase() === "true";
}

async function routeWithTimeout(input?: TestCognitionInput): Promise<CaliUcmAdapterResult> {
  return new Promise((resolve) => {
    const { Worker, isMainThread } = require('worker_threads');

    if (!isMainThread) {
      resolve({ routed: false, reason: 'CALI_UCM_DISABLED' } as any);
      return;
    }

    console.error(`[DIAG ${new Date().toISOString()}] stage=adapter_entry`);

    const workerCode = `
      const { parentPort, workerData } = require('worker_threads');
      const fs = require('fs');
      const logPath = 'R:/orb_mesh/exports/desktop/trace/cali_ucm_adapter_worker_diag.log';
      const diag = (stage) => {
        fs.appendFileSync(logPath, '[DIAG ' + new Date().toISOString() + '] stage=' + stage + '\\n');
        process.stderr.write('[DIAG ' + new Date().toISOString() + '] stage=' + stage + '\\n');
      };

      diag('worker_received_payload');
      diag('before_try');

      try {
        diag('try_entered');

        diag('require_resolve_ts_node_start');
        const tsNodePath = require.resolve('ts-node');
        diag('require_resolve_ts_node_complete:' + tsNodePath);

        diag('require_ts_node_start');
        const tsNode = require('ts-node');
        diag('require_ts_node_complete');

        diag('ts_node_register_start');
        tsNode.register({
          transpileOnly: true,
          project: 'R:/CALI-UCM/tsconfig.json',
          compilerOptions: { ignoreDeprecations: '6.0' }
        });
        diag('ts_node_register_complete');

        diag('require_resolve_runtime_start');
        const runtimePath = require.resolve('R:/CALI-UCM/IntegratedCore4Runtime.ts');
        diag('require_resolve_runtime_complete:' + runtimePath);

        diag('require_runtime_start');
        const caliUcm = require('R:/CALI-UCM/IntegratedCore4Runtime.ts');
        diag('require_runtime_complete');

        diag('runtime_construction_start');
        const runtime = new caliUcm.IntegratedCore4Runtime();
        diag('runtime_construction_complete');

        diag('step_start');
        const result = runtime.stepWithTransport(workerData && workerData.input);
        diag('step_complete');

        if (result && typeof result === 'object' && 'artifact' in result) {
          diag('core4_artifact_export_start');
          const artifact = result.artifact;
          diag('core4_artifact_export_complete');
        }

        diag('post_message_start');
        parentPort.postMessage({ success: true, result });
        diag('post_message_complete');
      } catch(e) {
        diag('worker_error:' + (e && e.message ? e.message : String(e)));
        parentPort.postMessage({ success: false, error: e && e.stack ? e.stack : e.message });
      }
    `;

    console.error(`[DIAG ${new Date().toISOString()}] stage=worker_spawned`);
    const worker = new Worker(workerCode, { eval: true, workerData: { input } });
    const timer = setTimeout(() => {
      worker.terminate();
      resolve({ routed: false, reason: 'CALI_UCM_TIMEOUT' } as any);
    }, 60000);

    worker.on('message', (msg: any) => {
      clearTimeout(timer);
      worker.terminate();
      if (msg.success) {
        resolve({ routed: true, source: 'CALI_UCM', result: msg.result });
      } else {
        resolve({ routed: false, reason: msg.error } as any);
      }
    });

    worker.on('error', (err: any) => {
      clearTimeout(timer);
      worker.terminate();
      resolve({ routed: false, reason: err.message } as any);
    });
  });
}

export class CaliUcmAdapter {
  private readonly enabled: boolean;

  constructor(config: CaliUcmAdapterConfig = {}) {
    this.enabled = config.enabled ?? flagEnabled(config.env);
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  async routeTestCognition(input?: TestCognitionInput): Promise<CaliUcmAdapterResult> {
    if (!this.enabled) {
      return {
        routed: false,
        reason: "CALI_UCM_DISABLED"
      };
    }

    return routeWithTimeout(input);
  }
}

export function createCaliUcmAdapter(config?: CaliUcmAdapterConfig): CaliUcmAdapter {
  return new CaliUcmAdapter(config);
}

export function isCaliUcmEnabled(env?: Record<string, string | undefined>): boolean {
  return flagEnabled(env);
}

export async function routeTestCognition(
  input?: TestCognitionInput
): Promise<CaliUcmAdapterResult> {
  if (process.env.CALI_UCM_ENABLED !== 'true') {
    return { routed: false, reason: 'CALI_UCM_DISABLED' };
  }
  return routeWithTimeout(input);
}
