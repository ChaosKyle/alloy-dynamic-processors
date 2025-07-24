#!/bin/bash

# Configuration Validation Script for Alloy Dynamic Processors
# This script validates Alloy River configurations for syntax, logic, and completeness

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONFIGS_DIR="alloy/configs"
TEMP_DIR="/tmp/alloy-validation"
EXIT_CODE=0

print_banner() {
    echo -e "${BLUE}"
    echo "=============================================="
    echo "  Alloy Configuration Validation"
    echo "=============================================="
    echo -e "${NC}"
}

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check if alloy binary is available
    if ! command -v alloy &> /dev/null; then
        print_error "Alloy binary not found. Please install Grafana Alloy:"
        echo "  go install github.com/grafana/alloy/cmd/alloy@latest"
        exit 1
    fi
    
    # Check if configs directory exists
    if [ ! -d "$CONFIGS_DIR" ]; then
        print_error "Configurations directory not found: $CONFIGS_DIR"
        exit 1
    fi
    
    # Create temp directory
    mkdir -p "$TEMP_DIR"
    
    print_status "Dependencies check completed ✓"
}

validate_syntax() {
    print_status "Validating configuration syntax..."
    
    local syntax_errors=0
    
    for config in "$CONFIGS_DIR"/*.river; do
        if [ ! -f "$config" ]; then
            print_warning "No .river files found in $CONFIGS_DIR"
            continue
        fi
        
        local config_name=$(basename "$config")
        echo -n "  Validating $config_name... "
        
        if alloy fmt --verify "$config" &> "$TEMP_DIR/${config_name}.syntax.log"; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗${NC}"
            print_error "Syntax errors in $config_name:"
            cat "$TEMP_DIR/${config_name}.syntax.log"
            syntax_errors=$((syntax_errors + 1))
        fi
    done
    
    if [ $syntax_errors -gt 0 ]; then
        print_error "$syntax_errors configuration(s) failed syntax validation"
        EXIT_CODE=1
    else
        print_status "All configurations passed syntax validation ✓"
    fi
}

validate_conversion() {
    print_status "Testing configuration conversion..."
    
    local conversion_errors=0
    
    for config in "$CONFIGS_DIR"/*.river; do
        if [ ! -f "$config" ]; then
            continue
        fi
        
        local config_name=$(basename "$config")
        echo -n "  Testing conversion for $config_name... "
        
        if alloy convert --source-format=alloy --target-format=alloy "$config" > "$TEMP_DIR/${config_name}.converted" 2> "$TEMP_DIR/${config_name}.conversion.log"; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗${NC}"
            print_error "Conversion failed for $config_name:"
            cat "$TEMP_DIR/${config_name}.conversion.log"
            conversion_errors=$((conversion_errors + 1))
        fi
    done
    
    if [ $conversion_errors -gt 0 ]; then
        print_error "$conversion_errors configuration(s) failed conversion test"
        EXIT_CODE=1
    else
        print_status "All configurations passed conversion test ✓"
    fi
}

validate_completeness() {
    print_status "Validating configuration completeness..."
    
    local completeness_errors=0
    
    for config in "$CONFIGS_DIR"/*.river; do
        if [ ! -f "$config" ]; then
            continue
        fi
        
        local config_name=$(basename "$config")
        echo -n "  Checking completeness of $config_name... "
        
        local errors=()
        
        # Check for essential components
        if ! grep -q "otelcol.receiver" "$config"; then
            errors+=("missing receiver configuration")
        fi
        
        if ! grep -q "otelcol.exporter" "$config"; then
            errors+=("missing exporter configuration")
        fi
        
        # Check for memory limiter (recommended for production)
        if ! grep -q "otelcol.processor.memory_limiter" "$config"; then
            errors+=("missing memory limiter (recommended)")
        fi
        
        # Check for batch processor (recommended for performance)
        if ! grep -q "otelcol.processor.batch" "$config"; then
            errors+=("missing batch processor (recommended)")
        fi
        
        # Check for output connections
        if ! grep -q "output {" "$config"; then
            errors+=("no output connections found")
        fi
        
        if [ ${#errors[@]} -eq 0 ]; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${YELLOW}⚠${NC}"
            for error in "${errors[@]}"; do
                print_warning "  $config_name: $error"
            done
            if [[ "${errors[*]}" =~ "missing" && ! "${errors[*]}" =~ "recommended" ]]; then
                completeness_errors=$((completeness_errors + 1))
            fi
        fi
    done
    
    if [ $completeness_errors -gt 0 ]; then
        print_error "$completeness_errors configuration(s) failed completeness validation"
        EXIT_CODE=1
    else
        print_status "All configurations passed completeness validation ✓"
    fi
}

validate_security() {
    print_status "Validating security configurations..."
    
    local security_issues=0
    
    for config in "$CONFIGS_DIR"/*.river; do
        if [ ! -f "$config" ]; then
            continue
        fi
        
        local config_name=$(basename "$config")
        echo -n "  Checking security of $config_name... "
        
        local issues=()
        
        # Check for hardcoded secrets
        if grep -i "password\|secret\|key\|token" "$config" | grep -v "env(" | grep -q "="; then
            issues+=("potential hardcoded credentials")
        fi
        
        # Check for insecure receivers (no TLS)
        if grep -A 10 "otelcol.receiver" "$config" | grep -q "endpoint.*:.*[0-9]" && ! grep -A 20 "otelcol.receiver" "$config" | grep -q "tls {"; then
            issues+=("receivers without TLS configuration")
        fi
        
        # Check for overly permissive network bindings
        if grep -q "0.0.0.0" "$config" && ! grep -q "tls {" "$config"; then
            issues+=("binding to all interfaces without TLS")
        fi
        
        if [ ${#issues[@]} -eq 0 ]; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${YELLOW}⚠${NC}"
            for issue in "${issues[@]}"; do
                print_warning "  $config_name: $issue"
            done
            security_issues=$((security_issues + 1))
        fi
    done
    
    if [ $security_issues -gt 0 ]; then
        print_warning "$security_issues configuration(s) have potential security issues"
    else
        print_status "All configurations passed security validation ✓"
    fi
}

validate_performance() {
    print_status "Validating performance configurations..."
    
    for config in "$CONFIGS_DIR"/*.river; do
        if [ ! -f "$config" ]; then
            continue
        fi
        
        local config_name=$(basename "$config")
        echo -n "  Checking performance of $config_name... "
        
        local recommendations=()
        
        # Check for memory limiter configuration
        if grep -q "otelcol.processor.memory_limiter" "$config"; then
            local limit=$(grep -A 5 "otelcol.processor.memory_limiter" "$config" | grep "limit_mib" | grep -o '[0-9]*')
            if [ -n "$limit" ] && [ "$limit" -lt 256 ]; then
                recommendations+=("memory limit might be too low (${limit}MB)")
            fi
        fi
        
        # Check for batch processor configuration
        if grep -q "otelcol.processor.batch" "$config"; then
            local batch_size=$(grep -A 5 "otelcol.processor.batch" "$config" | grep "send_batch_size" | grep -o '[0-9]*')
            if [ -n "$batch_size" ] && [ "$batch_size" -lt 100 ]; then
                recommendations+=("batch size might be too small (${batch_size})")
            fi
        fi
        
        if [ ${#recommendations[@]} -eq 0 ]; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${YELLOW}⚠${NC}"
            for rec in "${recommendations[@]}"; do
                print_warning "  $config_name: $rec"
            done
        fi
    done
}

run_custom_validations() {
    print_status "Running custom validations..."
    
    # Custom validation for AI sorter configuration
    if [ -f "$CONFIGS_DIR/ai_sorter.river" ]; then
        echo -n "  Validating AI sorter configuration... "
        
        if grep -q "otelcol.processor.routing" "$CONFIGS_DIR/ai_sorter.river" && \
           grep -q "from_attribute.*ai.forward_to" "$CONFIGS_DIR/ai_sorter.river"; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗${NC}"
            print_error "AI sorter configuration missing routing processor"
            EXIT_CODE=1
        fi
    fi
    
    # Custom validation for production configuration
    if [ -f "$CONFIGS_DIR/grafana-cloud-production.alloy" ]; then
        echo -n "  Validating production configuration... "
        
        if grep -q "memory_limiter" "$CONFIGS_DIR/grafana-cloud-production.alloy" && \
           grep -q "batch" "$CONFIGS_DIR/grafana-cloud-production.alloy"; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${YELLOW}⚠${NC}"
            print_warning "Production configuration missing recommended processors"
        fi
    fi
}

generate_report() {
    print_status "Generating validation report..."
    
    local report_file="$TEMP_DIR/validation-report.txt"
    
    cat > "$report_file" << EOF
Alloy Configuration Validation Report
=====================================
Generated: $(date)

Configuration Files Validated:
EOF
    
    for config in "$CONFIGS_DIR"/*.river; do
        if [ -f "$config" ]; then
            echo "  - $(basename "$config")" >> "$report_file"
        fi
    done
    
    echo "" >> "$report_file"
    echo "Validation Results:" >> "$report_file"
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "  Status: PASSED ✓" >> "$report_file"
        echo "  All configurations are valid and ready for deployment." >> "$report_file"
    else
        echo "  Status: FAILED ✗" >> "$report_file"
        echo "  Some configurations have issues that need to be addressed." >> "$report_file"
    fi
    
    echo "" >> "$report_file"
    echo "For detailed logs, check: $TEMP_DIR" >> "$report_file"
    
    if [ "$1" = "--report" ]; then
        cat "$report_file"
    fi
}

cleanup() {
    # Clean up temporary files older than 1 day
    find "$TEMP_DIR" -type f -mtime +1 -delete 2>/dev/null || true
}

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Validate Alloy River configurations for syntax, logic, and completeness"
    echo ""
    echo "Options:"
    echo "  --syntax         Only validate syntax"
    echo "  --security       Only validate security configurations"
    echo "  --performance    Only validate performance configurations"
    echo "  --report         Generate and display validation report"
    echo "  --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Run all validations"
    echo "  $0 --syntax           # Only check syntax"
    echo "  $0 --security         # Only check security"
    echo "  $0 --report           # Show detailed report"
}

# Main execution
main() {
    print_banner
    
    case "${1:-}" in
        --help)
            show_help
            exit 0
            ;;
        --syntax)
            check_dependencies
            validate_syntax
            ;;
        --security)
            check_dependencies
            validate_security
            ;;
        --performance)
            check_dependencies
            validate_performance
            ;;
        --report)
            check_dependencies
            validate_syntax
            validate_conversion
            validate_completeness
            validate_security
            validate_performance
            run_custom_validations
            generate_report --report
            ;;
        "")
            check_dependencies
            validate_syntax
            validate_conversion
            validate_completeness
            validate_security
            validate_performance
            run_custom_validations
            generate_report
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
    
    cleanup
    
    if [ $EXIT_CODE -eq 0 ]; then
        print_status "All validations completed successfully! ✓"
    else
        print_error "Validation failed with errors. Please review and fix the issues."
    fi
    
    exit $EXIT_CODE
}

# Run main function with all arguments
main "$@"