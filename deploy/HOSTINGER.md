# Deploying Ghosts of Wikipedia on a Hostinger VPS

This takes about 20 minutes, most of it waiting. Everything runs on one server: MariaDB, the API, the website,
and Caddy as the web server. The setup script is `deploy/hostinger_setup.sh` in this repo.

## 0. What you need

- A Hostinger VPS (KVM 2 is plenty: 2 vCPU, 8 GB RAM). The free Junction one works.
- Your **Featherless** key (for Gemma) and **Context.dev** key. Keep them out of git: paste them only on the server.
- About 20 minutes.

## 1. Put Ubuntu 24.04 on the server

The script is written and tested for **Ubuntu 24.04**. Newer versions (for example 26.04) may not have
MariaDB 12.3 packages yet.

1. hPanel → **VPS** → your server → **OS & Panel** → **Operating System**.
2. Choose plain **Ubuntu 24.04** (no control panel) and confirm. This wipes the server, which is fine on a new one.
3. Set a **root password** when asked and write it down.
4. Note the server's **IP address** (on the Overview page).

## 2. Open a terminal on the server

Either:
- hPanel → your server → **Web console** (top right), or
- PowerShell on your laptop: `ssh root@YOUR_IP` and enter the root password.

You should see a prompt ending in `#` (you are root).

## 3. Run the setup script

Paste these two lines, replacing the two `paste_here` values with your real keys:

```bash
curl -fsSL https://raw.githubusercontent.com/salomeshioshvili/ghosts_of_wikipedia/main/deploy/hostinger_setup.sh -o setup.sh
FEATHERLESS_API_KEY='paste_here' CONTEXT_DEV_API_KEY='paste_here' bash setup.sh
```

Optional, for HTTPS on your own domain (see step 7): put `DOMAIN='yourdomain.com'` at the front of the second line.

What it does (it prints each step as `==> 1/6 …` to `==> 6/6 …`):

1. System packages: git, Python, Node 22, Caddy, firewall
2. MariaDB 12.3 (falls back to 11.8), database `ghosts` and a user with a random password
3. Clones this repo to `/opt/ghosts` and writes `/opt/ghosts/.env` (keys + DB password, readable by root only)
4. Python packages and the website build
5. Starts the API as the `ghosts` service behind Caddy on port 80 (and 443 with a domain)
6. Starts loading the data in the background

At the end it prints **`Site: http://YOUR_IP/`**. That is your public link.

## 4. Use the same Gemma model as the laptop

```bash
echo 'TRANSLATE_MODEL=google/gemma-4-26B-A4B-it' >> /opt/ghosts/.env && systemctl restart ghosts
```

## 5. Wait for the data

```bash
tail -f /var/log/ghosts-prepare.log
```

The background job downloads the dataset, loads the revision history and processes articles in this order:

| Log line | What is ready after it |
|---|---|
| `demo articles 1150 1256 6021: 0 (exit)` | Civil War, Winter War, Mannerheim (the demo) |
| `50 hero articles` | the 50 featured articles on the homepage |
| `stats`, `coordination scores` | half-lives and scores |
| `English living / ghosts` | English translations for the demo articles |
| `=== ALL DONE` | everything |

Press **Ctrl+C** to stop watching; the job keeps running. Articles not processed yet are processed the
first time someone opens them (slower).

The server holds the demo and featured articles, not all 19,742 (that run took about 2 hours on a laptop).

## 6. Check it works

Open these in a browser:

- `http://YOUR_IP/`: the homepage
- `http://YOUR_IP/article/1150`: the Civil War article (press Play, click a dashed sentence)
- `http://YOUR_IP/languages?lang=fi&title=Talvisota`: the Winter War across languages

Then click **What could this mean?** and **Compare what each edition says** once on each demo topic.
The first click asks Gemma (about a minute); after that the answer is stored in MariaDB and loads instantly
for everyone. Do this before judges open the site.

## 7. Optional: a domain with HTTPS

1. hPanel → **Domains** → claim the free domain (or use your own).
2. In its DNS settings add an **A record**: name `@`, value `YOUR_IP`.
3. Wait until `ping yourdomain.com` shows your IP (minutes to an hour).
4. Point Caddy at the domain (replace `yourdomain.com`), and it gets the HTTPS certificate itself:

```bash
sed -i '1s/.*/yourdomain.com {/' /etc/caddy/Caddyfile && systemctl reload caddy
```

## Everyday commands

| Task | Command |
|---|---|
| Is the API running? | `systemctl status ghosts` |
| API logs | `journalctl -u ghosts -f` |
| Data loading progress | `tail -f /var/log/ghosts-prepare.log` |
| Restart after editing `.env` | `systemctl restart ghosts` |
| Update to the latest code | `cd /opt/ghosts && sudo -u ghosts git pull && sudo -u ghosts bash -c 'cd web && npm run build' && systemctl restart ghosts` |
| Database password | in `/opt/ghosts/.env` (only on the server) |

## Troubleshooting

- **The script stops at the MariaDB step.** The OS is probably not Ubuntu 24.04. Reinstall 24.04 (step 1) and run again.
- **The site shows "502 Bad Gateway".** The API isn't up yet or crashed: `journalctl -u ghosts -n 50` shows why.
- **An article page is slow the first time.** It is being processed on demand; the second visit is fast.
- **Gemma buttons say the key is missing.** Check `FEATHERLESS_API_KEY` in `/opt/ghosts/.env`, then `systemctl restart ghosts`.
- **"Live now" / "Still on the web?" say the key is missing.** Same for `CONTEXT_DEV_API_KEY`.
- **Running the script twice** keeps the database, its password and `.env`, but restarts the background
  data job from the start. To get new code, use the update command above instead.
