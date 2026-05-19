# Assistant AIO Discord Bot - Railway Deploy

## Required Railway Variable
Set this in Railway > Variables:

```env
DISCORD_BOT_TOKEN=your_new_discord_bot_token_here
```

Do not paste your token inside `main.py`.

## Railway Start Command
```bash
python main.py
```

## Discord Developer Portal Settings
Enable these bot privileged gateway intents:
- Server Members Intent
- Message Content Intent

The bot also needs permissions for slash commands, moderation, managing roles/channels/messages, and creating ticket channels.
