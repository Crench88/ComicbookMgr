# Port Masking Guide for Comic Book Manager

This guide shows you how to access your Flask application without showing port numbers in the URL.

## 🎯 **Goal**
Instead of: `http://localhost:5000`
You want: `http://localhost` or `http://comicbook.local`

## 📋 **Available Options**

### **Option 1: Run on Port 80 (Recommended)**
**Pros**: Simplest solution, no port number needed
**Cons**: Requires administrator privileges

```bash
# Run as administrator
python start_port80.py
```

**Access your app at:**
- `http://localhost`
- `http://comicbook.local`
- `http://comics.local`

### **Option 2: Use Port Forwarding**
**Pros**: No admin privileges needed, Flask runs on port 5000
**Cons**: More complex setup

```bash
python run_with_port_forwarding.py
```

**Access your app at:**
- `http://localhost` (forwards to port 5000)

### **Option 3: Use Nginx Reverse Proxy**
**Pros**: Production-ready, handles static files efficiently
**Cons**: Requires Nginx installation

1. Install Nginx
2. Copy `nginx.conf` to Nginx configuration
3. Start Nginx
4. Run Flask on port 5000

**Access your app at:**
- `http://localhost`

### **Option 4: Use a Different Port (443 for HTTPS)**
**Pros**: Standard HTTPS port
**Cons**: Still shows port if not 80

```python
app.run(debug=True, host='0.0.0.0', port=443)
```

## 🔧 **Setup Instructions**

### **For Option 1 (Port 80):**

1. **Run as Administrator:**
   ```bash
   python start_port80.py
   ```

2. **Access your app:**
   - `http://localhost`
   - `http://comicbook.local`

3. **Update Marvel API whitelist:**
   - Add: `comicbook.local`
   - Add: `localhost`

### **For Option 2 (Port Forwarding):**

1. **Run normally:**
   ```bash
   python run_with_port_forwarding.py
   ```

2. **Access your app:**
   - `http://localhost`

### **For Option 3 (Nginx):**

1. **Install Nginx**
2. **Configure Nginx:**
   ```bash
   # Copy nginx.conf to your Nginx sites-available
   sudo cp nginx.conf /etc/nginx/sites-available/comicbook
   sudo ln -s /etc/nginx/sites-available/comicbook /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

3. **Run Flask:**
   ```bash
   python app.py
   ```

## 🌐 **Marvel API Whitelisting**

Once you have a domain without port numbers, update your Marvel API whitelist:

1. Go to: https://developer.marvel.com/account
2. Add these domains:
   - `comicbook.local`
   - `localhost`
   - `127.0.0.1`

## 🚀 **Quick Start (Recommended)**

1. **Run the domain setup:**
   ```bash
   python setup_local_domain.py
   ```

2. **Start the app (as administrator):**
   ```bash
   python start_port80.py
   ```

3. **Access your app:**
   - `http://comicbook.local`

4. **Update Marvel API whitelist:**
   - Add: `comicbook.local`

## ✅ **Benefits**

- ✅ No port numbers in URLs
- ✅ Clean, professional URLs
- ✅ Marvel API whitelisting works
- ✅ Better user experience
- ✅ Easier to remember URLs

## 🔍 **Troubleshooting**

### **Permission Denied Error:**
- Run PowerShell/Command Prompt as Administrator
- Or use Option 2 (Port Forwarding)

### **Port Already in Use:**
- Check if another service is using port 80
- Use `netstat -an | findstr :80` to check
- Kill the process or use a different port

### **Domain Not Working:**
- Check hosts file: `C:\Windows\System32\drivers\etc\hosts`
- Ensure entries are correct
- Clear browser cache

## 📝 **Summary**

The **easiest solution** is Option 1 (Port 80):
1. Run `python start_port80.py` as administrator
2. Access at `http://comicbook.local`
3. Update Marvel API whitelist

This gives you clean URLs without port numbers! 🎉
