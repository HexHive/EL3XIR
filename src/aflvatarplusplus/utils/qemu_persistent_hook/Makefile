all:
	$(CC) -no-pie test.c -o test
	$(CC) -fPIC -shared read_into_rdi.c -o read_into_rdi.so
	$(CC) -fPIC -shared smc_persistent_hook.c -o smc_persistent_hook.so

clean:
	rm -rf in out test read_into_rdi.so smc_persistent_hook.so
