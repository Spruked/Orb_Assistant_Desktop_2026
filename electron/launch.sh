#!/bin/bash
# Launch script for CALI Floating Assistant Orb

echo "🚀 Starting CALI Floating Assistant Orb..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js first."
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Check if Tesseract is installed
if ! command -v tesseract &> /dev/null; then
    echo "⚠️  Tesseract OCR not found. Installing..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt update && sudo apt install -y tesseract-ocr
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install tesseract
    else
        echo "❌ Please install Tesseract OCR manually for your OS"
        echo "   Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
        exit 1
    fi
fi

# Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Build the React app
echo "🔨 Building React app..."
npm run build

# Start the Electron app
echo "🎯 Launching CALI Floating Orb..."
npm start