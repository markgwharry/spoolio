#!/bin/bash

echo "Building React frontend for production..."

# Navigate to frontend directory
cd frontend

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
fi

# Build the React app
echo "Building React app..."
npm run build

# Copy build files to static directory
echo "Copying build files to static directory..."
rm -rf ../static
cp -r build ../static

echo "Frontend build complete!"
echo "Static files are now in the 'static' directory"
