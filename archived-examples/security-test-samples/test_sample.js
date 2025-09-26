// Test file for JavaScript security vulnerabilities

// Used function
function usedFunction() {
  console.log('This function is used');
}

// Entry point
function main() {
  usedFunction();
}

if (require.main === module) {
  main();
}
