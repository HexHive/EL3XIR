
if(DEFINED IN_SOURCE_BUILD)
    set(LLVM_LINK_COMPONENTS BitWriter Core IPO IrReader InstCombine Instrumentation Target Linker Analysis ScalarOpts Support Svf)
    add_llvm_tool( smc_type_finder smc_type_finder.cpp )
else()
    add_executable( smc_type_finder smc_type_finder.cpp )

    target_link_libraries( smc_type_finder Svf ${llvm_libs} )

    set_target_properties( smc_type_finder PROPERTIES
                           RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin )
endif()
