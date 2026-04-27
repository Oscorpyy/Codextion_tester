# =============================================================================
# Makefile — Codexion tester setup
#
# Targets:
#   all     → make scripts executable (no relink on second run)
#   clean   → remove Python bytecode cache files
#   fclean  → clean + remove the build sentinel
#   re      → fclean then all
# =============================================================================

NAME    = tester
BUILT   = .built

SCRIPTS = tester.sh \
          src/run_tests.py \
          src/parse_logs.py \
          src/check_timing.py \
          src/check_makefile.py \
          src/utils.py

.PHONY: all clean fclean re

all: $(BUILT)

$(BUILT): $(SCRIPTS)
	@chmod +x tester.sh src/run_tests.py
	@touch $(BUILT)
	@echo "$(NAME): ready.  Run with: ./tester.sh [path/to/codexion]"

clean:
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true
	@find . -name "*.pyc" -delete 2>/dev/null; true
	@echo "$(NAME): cleaned."

fclean: clean
	@rm -f $(BUILT)
	@echo "$(NAME): fully cleaned."

re: fclean all
