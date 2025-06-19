# 📊 Quik Tracy

**A comprehensive tool for Tracy profiling with Docker and local support**

> Tracy is a real-time, nanosecond resolution, remote telemetry, hybrid frame and sampling profiler for games and other applications.

Quik Tracy provides a unified interface to build, capture, analyze, and export Tracy profiling data with support for both local executables and Docker containers.

## ✨ Features

- 🏗️ **Build Tracy Tools**: Automatically build Tracy tools locally or via Docker
- 📸 **Capture Profiles**: Capture profiling data from running applications
- 📊 **Export Data**: Convert Tracy traces to CSV format for analysis
- 🔍 **Profile Analysis**: Open traces in Tracy's GUI profiler or web interface
- 📈 **Generate Reports**: Create HTML and HDF5 reports from trace data
- 🚀 **Complete Sessions**: Run end-to-end profiling workflows
- 🐋 **Docker Support**: Full containerized workflow support
- 🏠 **Local Support**: Native executable support for maximum performance

## 📋 Requirements

### System Requirements
- **Python 3.10+**
- **Docker** (optional, for containerized workflows)
- **Git** (for local builds)
- **CMake & Build tools** (for local builds)

### Tracy Application Requirements
Your application must be instrumented with Tracy profiling macros. See the [Tracy documentation](https://github.com/wolfpld/tracy) for details.

## 🚀 Installation

### Install from PyPI (Coming Soon)
```bash
pip install quik-tracy
```

### Install from Source
```bash
git clone https://github.com/mtreglia-gpsw/quik-tracy.git
pip install -e quik-tracy
```

### Verify Installation
```bash
quik-tracy --help
```

## 🛠️ Building Tracy Tools

Before using Quik Tracy, you need to build the Tracy tools. The tool supports both local compilation and Docker-based builds.

### Check Build Status
```bash
# Check what tools and builders are available
quik-tracy build status
```

### Build All Tools
```bash
# Auto-detect best build method (local preferred, Docker fallback)
quik-tracy build all

# Force local build (requires cmake, git, build tools)
quik-tracy build all --mode local

# Force Docker build (requires Docker)
quik-tracy build all --mode docker
```

### Build Individual Tools
```bash
# Build specific tools
quik-tracy build capture
quik-tracy build csvexport  
quik-tracy build profiler  # Note: Docker mode only supports Chrome browser and offline traces
```

### Custom Tracy Version
```bash
# Build from specific Tracy branch/commit
quik-tracy build all --branch master --ref 7e833e7ddce8bb36476b0452b2823c000dfad02b
```

## 📸 Capturing Profiles

### Basic Capture
```bash
# Capture from an application running on localhost:8086
quik-tracy capture

# Custom file name and location
quik-tracy capture --name my-profile.tracy --path ./profiles/

# Capture from remote application
quik-tracy capture --host 192.168.1.100 --port 8086
```

### Capture Modes
```bash
# Auto-detect best capture method
quik-tracy capture --mode auto

# Use local tracy-capture executable
quik-tracy capture --mode local

# Use Docker container
quik-tracy capture --mode docker
```

## 📊 Exporting Data

Convert Tracy trace files to CSV format for further analysis:

```bash
# Export trace to CSV
quik-tracy export my-profile.tracy

# Export with custom output directory
quik-tracy export my-profile.tracy --path ./exports/

# Force specific export mode
quik-tracy export my-profile.tracy --mode docker
```

## 🔍 Profile Analysis

### GUI Profiler
```bash
# Open trace in Tracy's native GUI profiler
quik-tracy profiler my-profile.tracy

# Connect to live application for real-time profiling
quik-tracy profiler --host localhost --port 8086
```

### Web Interface (Docker)
```bash
# Launch web-based profiler (requires Docker)
quik-tracy profiler my-profile.tracy --mode docker
# Then open http://localhost:8000 in Chrome/Chromium
```

> **⚠️ Warning: Docker Profiler Limitations**
> 
> The Docker-based WASM HTML Server Tracy profiler has the following restrictions:
> - **Browser Support**: Only Chrome/Chromium browsers are supported
> - **Offline Only**: Only supports offline trace file analysis (no live capture)
> - **Live Profiling**: For real-time profiling, use `--mode local` instead

## 📈 Generating Reports

Create analysis reports from exported CSV data:

```bash
# Generate HTML report
quik-tracy report my-profile.csv

# Generate HDF5 report for programmatic access
quik-tracy report my-profile.csv --mode hdf5

# Custom output directory
quik-tracy report my-profile.csv --path ./reports/
```

## 🔄 Comparing Multiple Traces

Compare multiple Tracy trace files to analyze performance changes between runs:

```bash
# Basic usage: compare two or more trace files
quik-tracy compare baseline.tracy optimized.tracy

# Compare CSVs directly
quik-tracy compare baseline.csv optimized.csv

# Specify output format (HTML or HDF5)
quik-tracy compare baseline.tracy optimized.tracy --mode html

# Custom output directory
quik-tracy compare baseline.tracy optimized.tracy --path ./comparisons/

# Custom output file name (without extension)
quik-tracy compare baseline.tracy optimized.tracy --name my-comparison
```

**Options:**
- `TRACE_FILES` (required): Two or more `.tracy` or `.csv` files to compare.
- `--mode [hdf5|html]`: Output format for the comparison report (default: `html`).
- `--path PATH`: Directory to save the comparison report (default: current directory).
- `--name TEXT`: Custom name for the output comparison report file (without extension).

The output will be saved as `my-comparison.html` or `my-comparison.h5` if `--name my-comparison` is provided, otherwise a default name is used.

**Example output:**  
- [View the HTML source on GitHub](./examples/tracy_comparison_example.html)  
- [View the rendered report (via githack.com)](https://raw.githack.com/mtreglia-gpsw/quik-tracy/main/examples/tracy_comparison_example.html)

> **Note:**  
> GitHub displays HTML files as source code. To see the report as a web page, use the githack.com link above or download the file and open it in your browser.

## 🚀 Complete Sessions

Run end-to-end profiling workflows:

```bash
# Complete workflow: capture → export → report
quik-tracy session

# Custom session with specific modes
quik-tracy session \
    --name production-profile.tracy \
    --capture-mode docker \
    --export-mode process \
    --report-mode html \
    --path ./session-output/
```

## 📁 Output Structure

Quik Tracy creates organized output structures:

```
./
├── capture.tracy              # Raw Tracy capture file
├── capture.csv               # Exported CSV data
├── capture.h5                # HDF5 report (if generated)
├── capture.html              # HTML report (if generated)
└── tracy_session_YYYY.MM.DD_HH.MM.SS/  # Session output
    ├── session.tracy
    ├── session.csv
    └── session.html
```

## 🔧 Configuration

### Tool Locations

**Local builds**: Tools are installed to `~/.quik-tracy/install/bin/`
**Docker builds**: Tools run in containers with automatic volume mounts

## 🐋 Docker Workflow

For fully containerized environments:

```bash
# Build all tools as Docker images
quik-tracy build all --mode docker

# Run complete containerized workflow
quik-tracy session --capture-mode docker --export-mode docker

# Launch web profiler for browser-based analysis
quik-tracy profiler --mode docker
```

## 🛠️ Local Development

For native performance and development:

```bash
# Build tools locally
quik-tracy build all --mode local

# Use local executables (fastest)
quik-tracy session --capture-mode process --export-mode process
```

## 📚 Examples

### Profiling a Local Application
```bash
# 1. Instrument your app with Tracy and run it
./my-app  # Should connect to Tracy on port 8086

# 2. Capture profile data
quik-tracy capture --name my-app-profile.tracy

# 3. Analyze in GUI
quik-tracy profiler my-app-profile.tracy

# 4. Generate report
quik-tracy export my-app-profile.tracy
quik-tracy report my-app-profile.csv
```

### Profiling a Containerized Application
```bash
# 1. Run your containerized app with Tracy
docker run -p 8086:8086 my-app:latest

# 2. Complete session with Docker tools
quik-tracy session \
    --name containerized-profile.tracy \
    --host host.docker.internal \
    --capture-mode docker \
    --export-mode docker
```

### Complete Session Example
```bash
# Run a complete session that produces organized output
quik-tracy session

# This creates a timestamped folder with all outputs:
# tracy_session_2025.06.09_23.54.44/
# ├── capture.csv
# ├── capture.h5  
# ├── capture.html
# └── capture.tracy
```

### Performance Analysis Workflow
```bash
# 1. Capture multiple profiles
quik-tracy capture --name baseline.tracy
# ... make changes to your app ...
quik-tracy capture --name optimized.tracy

# 2. Export both for comparison
quik-tracy export baseline.tracy
quik-tracy export optimized.tracy

# 3. Generate comparative reports
quik-tracy report baseline.csv --path ./reports/
quik-tracy report optimized.csv --path ./reports/
```

## 🔍 Troubleshooting

### Build Issues
```bash
# Check build environment
quik-tracy build status

# Force rebuild
quik-tracy build all --mode local  # or --mode docker
```

### Capture Issues
```bash
# Verify Tracy is running in your application
# Check network connectivity
ping host.docker.internal  # For Docker setups

# Try different modes
quik-tracy capture --mode local  # or --mode docker
```

### Docker Issues
```bash
# Verify Docker is running
docker ps

# Check Tracy images
docker images | grep tracy

# Rebuild images if needed
quik-tracy build all --mode docker
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [Tracy Profiler](https://github.com/wolfpld/tracy)

## 📞 Support

- 📖 Documentation: See inline help with `quik-tracy <command> --help`
- 🐛 Issues: Report issues on the project repository  
- 💬 Discussions: Join the project discussions

---

**Happy Profiling! 🚀**
