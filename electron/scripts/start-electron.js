const { spawn } = require('child_process');
const electronBinary = require('electron');

const extraArgs = process.argv.slice(2);
const electronArgs = ['.', ...extraArgs, '--disable-http-cache'];

delete process.env.ELECTRON_RUN_AS_NODE;

const child = spawn(electronBinary, electronArgs, {
  stdio: 'inherit',
  env: process.env,
  cwd: require('path').resolve(__dirname, '..'),
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

