# cat > /home/claude/smart-url-shortener/utils.py << 'EOF'
import random
import string

def generate_short_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))
# EOF

# echo "Core files written"
# Output

# Core files written