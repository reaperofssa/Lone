import express from 'express';
import { exec } from 'child_process';
import fs from 'fs-extra';
import path from 'path';

const app = express();
const PORT = process.env.PORT || 3000;
const CLONE_DIR = path.resolve('./cloned_repos');
const LOGS_DIR = path.resolve('./logs');

// Ensure directories exist
fs.ensureDirSync(CLONE_DIR);
fs.ensureDirSync(LOGS_DIR);

// Helper function to stream command output to the terminal
function streamLogs(command, cwd, logFile, res) {
  const process = exec(command, { cwd });

  process.stdout.on('data', (data) => {
    fs.appendFileSync(logFile, data);
    res.write(data);
  });

  process.stderr.on('data', (data) => {
    fs.appendFileSync(logFile, data);
    res.write(data);
  });

  process.on('close', (code) => {
    res.end(`\nProcess completed with code: ${code}`);
  });

  process.on('error', (err) => {
    fs.appendFileSync(logFile, err.message);
    res.end(`\nError: ${err.message}`);
  });
}

// Start command
app.get('/start', (req, res) => {
  const { number } = req.query;

  if (!number) {
    return res.status(400).json({ message: 'Number is required.' });
  }

  const repoPath = path.join(CLONE_DIR, number);
  const logFile = path.join(LOGS_DIR, `${number}.log`);

  if (!fs.existsSync(repoPath)) {
    const repoUrl = 'https://github.com/reaperofssa/kaiju'; // Replace with your GitHub repo URL

    exec(`git clone ${repoUrl} ${repoPath}`, (err) => {
      if (err) {
        fs.appendFileSync(logFile, err.message);
        return res.status(500).json({ message: `Error cloning repo: ${err.message}` });
      }

      // Link to backend's node_modules
      const nodeModulesPath = path.resolve('./node_modules');
      const linkedNodeModulesPath = path.join(repoPath, 'node_modules');
      if (!fs.existsSync(linkedNodeModulesPath)) {
        fs.symlinkSync(nodeModulesPath, linkedNodeModulesPath, 'dir');
      }

      // Create a package.json if it doesn't exist
      const packageJsonPath = path.join(repoPath, 'package.json');
      if (!fs.existsSync(packageJsonPath)) {
        fs.writeJsonSync(packageJsonPath, {
          name: `repo-${number}`,
          version: '1.0.0',
          main: 'index.js',
          scripts: { start: 'node index.js' },
        });
      }

      // Start index.js
      res.setHeader('Content-Type', 'text/plain');
      streamLogs(`npm start`, repoPath, logFile, res);
    });
  } else {
    res.setHeader('Content-Type', 'text/plain');
    streamLogs(`npm start`, repoPath, logFile, res);
  }
});

// Delete command
app.get('/delete', (req, res) => {
  const { number } = req.query;

  if (!number) {
    return res.status(400).json({ message: 'Number is required.' });
  }

  const repoPath = path.join(CLONE_DIR, number);
  const logFile = path.join(LOGS_DIR, `${number}.log`);

  if (!fs.existsSync(repoPath)) {
    return res.json({ message: 'Directory does not exist.' });
  }

  fs.remove(repoPath, (err) => {
    if (err) {
      fs.appendFileSync(logFile, err.message);
      return res.status(500).json({ message: `Error: ${err.message}` });
    }

    fs.removeSync(logFile); // Optionally delete logs for the number
    res.json({ message: 'Directory deleted successfully.' });
  });
});

app.listen(PORT, () => console.log(`Backend running on port ${PORT}`));
