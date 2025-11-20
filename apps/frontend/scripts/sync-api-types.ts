#!/usr/bin/env node
/**
 * Sync API Types from Backend
 *
 * This script fetches the OpenAPI schema from the backend repository,
 * generates TypeScript types, and compares them with the committed types.
 *
 * Usage:
 *   pnpm sync-types          # Check if types are in sync
 *   pnpm sync-types --update # Update types from backend
 */

import { execSync } from 'child_process';
import {
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  unlinkSync
} from 'fs';
import { join, dirname, resolve } from 'path';

// Validate and sanitize backend repo path
function validateBackendPath(path: string): string {
  // Resolve to absolute path to prevent directory traversal
  const resolvedPath = resolve(path);

  // Basic validation: ensure it's a valid path format
  if (resolvedPath.includes('\0')) {
    throw new Error('Invalid backend repository path: contains null bytes');
  }

  return resolvedPath;
}

const BACKEND_REPO_PATH = validateBackendPath(
  process.env.BACKEND_REPO_PATH || '../backend' // In monorepo: resolves to apps/backend from apps/frontend
);
// In monorepo structure, openapi.json is at apps/backend/openapi.json
const BACKEND_OPENAPI_PATH = join(BACKEND_REPO_PATH, 'openapi.json');
const FRONTEND_TYPES_PATH = join(
  process.cwd(),
  'src',
  'lib',
  'generated',
  'api-types.ts'
);
const TEMP_TYPES_PATH = join(process.cwd(), 'tmp-api-types.ts');

const shouldUpdate = process.argv.includes('--update');
const isCI = process.env.CI === 'true';

function log(message: string) {
  console.log(`[sync-api-types] ${message}`);
}

function error(message: string) {
  console.error(`[sync-api-types] ❌ ${message}`);
}

function success(message: string) {
  console.log(`[sync-api-types] ✅ ${message}`);
}

function executeCommand(command: string, cwd?: string): string {
  try {
    // Validate and sanitize cwd if provided
    const workingDir = cwd ? resolve(cwd) : process.cwd();

    // Basic security check: ensure no null bytes
    if (workingDir.includes('\0')) {
      throw new Error('Invalid working directory: contains null bytes');
    }

    return execSync(command, {
      cwd: workingDir,
      encoding: 'utf-8',
      stdio: 'pipe'
    }).trim();
  } catch (err: any) {
    throw new Error(`Command failed: ${command}\n${err.message}`);
  }
}

function checkBackendRepo(): boolean {
  if (!existsSync(BACKEND_REPO_PATH)) {
    error(`Backend repository not found at ${BACKEND_REPO_PATH}`);
    error('Make sure the backend repo is cloned at the expected location.');
    return false;
  }
  log(`Found backend repo at ${BACKEND_REPO_PATH}`);
  return true;
}

function generateOpenAPISchema() {
  log('Generating OpenAPI schema from backend...');

  const pythonScript = `
import sys
import json
import io
from pathlib import Path

# Add src directory to Python path for meridinate package
src_dir = Path.cwd() / 'src'
sys.path.insert(0, str(src_dir))

# Suppress FastAPI startup logs by redirecting stdout
old_stdout = sys.stdout
sys.stdout = io.StringIO()

from meridinate.main import create_app

# Restore stdout
sys.stdout = old_stdout

app = create_app()
schema = app.openapi()

with open('openapi.json', 'w') as f:
    json.dump(schema, f, indent=2)

print('OpenAPI schema exported successfully!')
`;

  const configPath = join(BACKEND_REPO_PATH, 'config.json');
  const settingsPath = join(BACKEND_REPO_PATH, 'api_settings.json');
  const monitoredPath = join(BACKEND_REPO_PATH, 'monitored_addresses.json');

  // Create test config files if they don't exist
  // Using flag 'wx' to write only if file doesn't exist (atomic operation)
  try {
    writeFileSync(configPath, JSON.stringify({ helius_api_key: 'test-key' }), {
      flag: 'wx'
    });
  } catch (err: any) {
    if (err.code !== 'EEXIST') throw err;
  }

  try {
    writeFileSync(
      settingsPath,
      JSON.stringify({ walletCount: 5, concurrentAnalysis: 3 }),
      { flag: 'wx' }
    );
  } catch (err: any) {
    if (err.code !== 'EEXIST') throw err;
  }

  try {
    writeFileSync(monitoredPath, JSON.stringify([]), { flag: 'wx' });
  } catch (err: any) {
    if (err.code !== 'EEXIST') throw err;
  }

  // Execute Python script via stdin to avoid command injection and temp files
  try {
    // Use venv Python on Windows, fallback to system python
    const pythonCmd =
      process.platform === 'win32'
        ? join(BACKEND_REPO_PATH, '.venv', 'Scripts', 'python.exe')
        : 'python3';

    execSync(pythonCmd, {
      cwd: BACKEND_REPO_PATH,
      encoding: 'utf-8',
      stdio: 'pipe',
      input: pythonScript
    });

    success('OpenAPI schema generated');
  } catch (err: any) {
    error(`Failed to generate OpenAPI schema: ${err.message}`);
    throw err;
  }
}

function generateTypeScriptTypes() {
  log('Generating TypeScript types from OpenAPI schema...');

  try {
    // Check if openapi-typescript is installed
    try {
      executeCommand('npx openapi-typescript --version');
    } catch {
      log('Installing openapi-typescript...');
      executeCommand('npm install -g openapi-typescript');
    }

    // Properly quote paths to prevent command injection
    executeCommand(
      `npx openapi-typescript "${BACKEND_OPENAPI_PATH}" -o "${TEMP_TYPES_PATH}"`
    );

    // Get backend commit SHA for version tracking
    let backendCommitSha = '';
    try {
      backendCommitSha = executeCommand(
        'git rev-parse HEAD',
        BACKEND_REPO_PATH
      );
      log(`Backend commit: ${backendCommitSha.substring(0, 7)}`);
    } catch (err: any) {
      log('Warning: Could not get backend commit SHA');
    }

    // Add header comment with backend commit SHA
    log('Adding version tracking header...');
    const originalContent = readFileSync(TEMP_TYPES_PATH, 'utf-8');
    const headerComment = `/**
 * Auto-generated TypeScript types from Backend OpenAPI schema
 * Backend Commit: ${backendCommitSha || 'unknown'}
 * DO NOT EDIT - This file is auto-generated
 */

`;
    writeFileSync(TEMP_TYPES_PATH, headerComment + originalContent);

    // Format the generated types with prettier to match project style
    log('Formatting generated types...');
    // Read the generated file and manually fix formatting
    let content = readFileSync(TEMP_TYPES_PATH, 'utf-8');
    // Convert 4-space indentation to 2-space
    content = content.replace(/^(    )+/gm, (match) =>
      '  '.repeat(match.length / 4)
    );
    // Write back the formatted content
    writeFileSync(TEMP_TYPES_PATH, content);
    // Run prettier to finalize formatting (properly quoted path)
    // Note: Respects project's .prettierrc configuration for consistency
    executeCommand(`pnpm exec prettier --write "${TEMP_TYPES_PATH}"`);

    success('TypeScript types generated');
  } catch (err: any) {
    error(`Failed to generate TypeScript types: ${err.message}`);
    throw err;
  }
}

function compareTypes(): boolean {
  if (!existsSync(FRONTEND_TYPES_PATH)) {
    log('No existing types found in frontend');
    return false;
  }

  // Normalize line endings and type representations for comparison
  const normalize = (str: string) =>
    str
      .replace(/\r\n/g, '\n') // Windows CRLF -> LF
      .replace(/Record<string, never>/g, '{ [key: string]: unknown }') // openapi-typescript platform difference
      .replace(
        /\{\s+\[key: string\]: unknown;\s+\}/g,
        '{ [key: string]: unknown }'
      ) // normalize multi-line type objects
      .replace(/"/g, "'"); // normalize all double quotes to single quotes (safe in type definitions)

  const existingTypes = normalize(readFileSync(FRONTEND_TYPES_PATH, 'utf-8'));
  const newTypes = normalize(readFileSync(TEMP_TYPES_PATH, 'utf-8'));

  if (existingTypes !== newTypes) {
    // Debug: show first difference
    for (let i = 0; i < Math.min(existingTypes.length, newTypes.length); i++) {
      if (existingTypes[i] !== newTypes[i]) {
        const start = Math.max(0, i - 50);
        const end = Math.min(existingTypes.length, i + 50);
        log(`First diff at position ${i}:`);
        log(`Existing: ${JSON.stringify(existingTypes.substring(start, end))}`);
        log(`New: ${JSON.stringify(newTypes.substring(start, end))}`);
        break;
      }
    }
    if (existingTypes.length !== newTypes.length) {
      log(
        `Length mismatch: existing=${existingTypes.length}, new=${newTypes.length}`
      );
    }
  }

  return existingTypes === newTypes;
}

function updateTypes() {
  log('Updating frontend types...');

  // Ensure directory exists
  const dir = dirname(FRONTEND_TYPES_PATH);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  const newTypes = readFileSync(TEMP_TYPES_PATH, 'utf-8');
  writeFileSync(FRONTEND_TYPES_PATH, newTypes);

  // Clean up temp file using Node.js API instead of shell command
  if (existsSync(TEMP_TYPES_PATH)) {
    unlinkSync(TEMP_TYPES_PATH);
  }

  success(`Types updated at ${FRONTEND_TYPES_PATH}`);
}

function main() {
  log('Starting API types sync...');
  log(`Mode: ${shouldUpdate ? 'UPDATE' : 'CHECK'}`);

  try {
    // Step 1: Check backend repo exists
    if (!checkBackendRepo()) {
      process.exit(1);
    }

    // Step 2: Generate OpenAPI schema from backend
    generateOpenAPISchema();

    // Step 3: Generate TypeScript types
    generateTypeScriptTypes();

    // Step 4: Compare or update
    if (shouldUpdate) {
      updateTypes();
      success('API types sync completed successfully!');
      success('Remember to commit the updated types.');
    } else {
      const inSync = compareTypes();

      if (inSync) {
        success('API types are in sync with backend! ✨');
      } else {
        error('API types are out of sync with backend!');
        error('');
        error('To update the types, run:');
        error('  pnpm sync-types --update');
        error('');

        if (isCI) {
          error(
            'In CI: Types must be kept in sync. Please update and commit them.'
          );
        }

        process.exit(1);
      }
    }
  } catch (err: any) {
    error(`Sync failed: ${err.message}`);
    process.exit(1);
  }
}

main();
