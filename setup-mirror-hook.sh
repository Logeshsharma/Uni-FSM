#!/bin/bash

HOOK_DIR=".git/hooks"
HOOK_FILE="$HOOK_DIR/post-push"

echo "Setting up post-push hook to auto-mirror to GitHub..."

mkdir -p "$HOOK_DIR"

cat > "$HOOK_FILE" << 'EOF'
#!/bin/bash
echo "🔁 Mirroring to GitHub..."
git push --mirror github-mirror
echo "✅ Mirror completed."
EOF

chmod +x "$HOOK_FILE"

echo "Post-push hook installed successfully!"
