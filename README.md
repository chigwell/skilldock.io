<div align="center">
  <a target="_blank" href="https://skilldock.io/?utm_source=github&utm_medium=readme">
   <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=200&section=header&text=SkillDock.io&fontSize=50&fontAlignY=35&animation=fadeIn&fontColor=FFFFFF&descAlignY=55&descAlign=62" alt="SkillDock" width="100%" />
  </a>
</div>

Empower your agent with skills.

SkillDock.io is a registry of reusable AI skills built around the AgentSkills specification, so skills can work across different agent runtimes.

SkillDock helps you discover and install community-published skills, so you can add proven capabilities to your agents quickly and consistently.

Skill authors use SkillDock to publish and version skills with clear metadata and releases, making them easy to find, install, and run in OpenClaw, Claude, or any other agent that supports skills.

## Links

- Website: [https://skilldock.io](https://skilldock.io)
- PyPI package: [https://pypi.org/project/skilldock/](https://pypi.org/project/skilldock/)

[![PyPI version](https://badge.fury.io/py/skilldock.svg)](https://badge.fury.io/py/skilldock)
[![License: MIT](https://img.shields.io/badge/License-Apache2.0-green.svg)](https://opensource.org/license/apache-2-0)
[![Downloads](https://static.pepy.tech/badge/skilldock)](https://pepy.tech/project/skilldock)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-blue)](https://www.linkedin.com/in/eugene-evstafev-716669181/)

## Install the CLI

```bash
pip install skilldock
```

## How to use SkillDock

1. Search skills in the registry.
2. Pick a skill and install it with the SkillDock package.
3. Keep skills up to date with automatic version and dependency updates.
4. Copy a ready-to-use integration prompt and paste it into your agent/LLM.

One prompt, any agent: once installed, SkillDock skills can be reused across compatible runtimes.

## About this repository

This repository contains the SkillDock.io landing and discovery site built with Next.js.

## Local development

Run the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Cloudflare deployment

This repo is configured for Cloudflare via OpenNext and Wrangler.

API base URL defaults to `https://api.skilldock.io`. You can override it with:

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.skilldock.io
```

1. Authenticate Wrangler:

```bash
npx wrangler login
```

2. Build and preview locally with Wrangler:

```bash
npm run preview:cf
```

3. Deploy to Cloudflare Workers:

```bash
npm run deploy:cf
```
