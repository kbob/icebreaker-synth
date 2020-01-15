help:
	@echo No help.

clean:
	@set -e;							\
	find * -name \*.gtkw -o -name \*.vcd                            \
	| while read f;		                                        \
	do								\
	    echo rm -f $$f;						\
	    rm -f "$$f";						\
	done
	@set -e;							\
	find * -type d \( -name build -o -name __pycache__ \)		\
        | while read d;							\
	    do								\
	    echo rm -rf $$d;						\
	    rm -rf "$$d";						\
	done
