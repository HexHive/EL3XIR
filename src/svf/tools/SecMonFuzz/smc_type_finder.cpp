// The tool smc_type_finder is capable of extracting type/semantic information
// of the parameters of executed SMCs
// from a given (partial) linux kernel

// IN: A linux kernel module / partially linked in LLVM Bitcode
// OUT: Semantic information of each register x0 - x6 when SMCs are executed

#include "Graphs/SVFG.h"
#include "WPA/Andersen.h"
#include "Util/Options.h"
#include "Util/SVFUtil.h"
#include "SVF-LLVM/SVFIRBuilder.h"
#include "SVF-LLVM/LLVMUtil.h"

using namespace llvm;
using namespace std;
using namespace SVF;

static llvm::cl::opt<std::string> InputFilename(llvm::cl::Positional,
        llvm::cl::desc("<input bitcode>"), llvm::cl::init("-"));

struct smcArg {
    unsigned int idx;
    unsigned long constant;
    DIType *type;

    // equality comparison. doesn't modify object. therefore const.
    bool operator==(const smcArg& a) const
    {
        // && !(std::includes(constant.begin(), constant.end(), a.constant.begin(), a.constant.end()))
        return (idx == a.idx);
    }
};

unsigned long getConstValue(const SVFValue *v)   {
    assert(v->isConstDataOrAggData());
    size_t start_idx = v->toString().find(" ", 1) + 1;
    size_t end_idx = v->toString().find(" {");
    std::string conststr = v->toString().substr(start_idx, (end_idx-start_idx));
    //cout << "TO CONST: " << conststr << "\n";
    //cout.flush();
    if(conststr != "null" && conststr != "true" && conststr != "false")  {
        // TODO: change all constant to unsigned int?
        unsigned int constvalue = std::stoul(conststr, nullptr, 0);
        return constvalue;
    }
    return 0;
}

void dumpToCSV(Map<const SVFBasicBlock *, std::list<smcArg>> *smcArgMap, char *outpath)   {
    std::ofstream outfile;
    outfile.open(outpath);
    //cout << "\nWriting a total of " << smcArgMap->size() << " options for harness to CSV result file!\n";
    outfile << "BB or Index, Constants, Type\n";

    // TODO: we could filter out some obvious false positives e.g. options with no x0 value
    for(Map<const SVFBasicBlock*, std::list<smcArg>>::iterator iter = smcArgMap->begin(); iter != smcArgMap->end(); iter++)   {
        //cout << "Writing CSV for BB: " << iter->first->toString() << "\n";
        /*if(iter->first->toString().find(".h") != std::string::npos ||
            iter->second.size() <= 2 || iter->second.size() >= 9)    {
            // sort out some small ones
            continue;
        }*/
        unsigned int currIdx = 0;
        for(list<smcArg>::iterator smcargs = iter->second.begin(); smcargs != iter->second.end(); smcargs++) {
            if(currIdx == (*smcargs).idx)   {
                /*if(currIdx == 0 && (*smcargs).constant == 0)    {
                    break;
                }
                if(currIdx == 0 && (*smcargs).constant == UINT64_MAX)    {
                    break;
                }*/
                if(currIdx == 0)   {
                    outfile << iter->first->toString() << "\n";
                }
                // we have an entry for that index
                outfile << (*smcargs).idx << ",";
                if((*smcargs).constant == UINT64_MAX)   {
                    outfile << " " << ",";
                    // we are only interested in the type if we got no constant
                    if((*smcargs).type != nullptr && !(*smcargs).type->getName().str().empty())  {
                        outfile << (*smcargs).type->getName().str();
                    }
                    else    {
                        outfile << "u64";
                    }
                }
                else    {
                    outfile << (*smcargs).constant << ",";
                    // also add type for not x0 TEST
                    if(currIdx > 0) {
                        if((*smcargs).type != nullptr && !(*smcargs).type->getName().str().empty())  {
                            outfile << (*smcargs).type->getName().str();
                        }
                        else    {
                            outfile << "u64";
                        }
                    }
                }
                outfile << "\n";
            }
            else    {
                if(currIdx == 0)    {
                    break;
                    //outfile << iter->first->toString() << "\n";
                }
                // we have no entry so just write the default one
                outfile << currIdx << ",";
                outfile << " " << ",";
                outfile << "u64" << "\n";
            }
            currIdx += 1;
        }
    }
    // add one generic option
    outfile << "BasicBlock:...\n";
    for(unsigned long i = 0; i < 8; i++)   {
        if(i == 0)  {
            outfile << i << "," << " " << "," << "u32" << "\n";
        }
        else    {
            outfile << i << "," << " " << "," << "u64" << "\n";
        }
    }
    outfile.close();
    //cout << "Written CSV to outfile!\n";
}

// Start to InitSink
// use a heuristic to identify potential SMC CallSites - used later to get arguments
std::list<SVF::CallSite> getSmcCallSiteCandidates(SVFModule* svfModule) {
    std::list<SVF::CallSite> candidateSmcCS;

    // we identify potential SMC callsites by going through all instructions
    // go through all functions
    for (SVFModule::const_iterator F = svfModule->begin(), E = svfModule->end(); F != E; ++F)  {
        // get current function as LLVM::Function
        //Function *curr = LLVMModuleSet::getLLVMModuleSet()->getSVFFunction(*F)->getLLVMFun();
        const SVFFunction *curr = (*F);
        
        // go through each basic block
        for(SVFFunction::const_iterator B = curr->begin(), BE = curr->end(); B != BE; ++B)  {
            const SVFBasicBlock *curr_bb = (*B);
            // go through each instruction
            for(SVFBasicBlock::const_iterator I = curr_bb->begin(), J = curr_bb->end(); I != J; ++I)    {
                const SVFInstruction *inst = (*I);

                // filter out all llvm intrinsic stuff e.g. "call void @llvm.dbg.value"
                // and check if the current instruction is a callsite
                if (SVFUtil::isNonInstricCallSite(inst) && inst->toString().find("llvm") == std::string::npos)    {
                
                    // get callsite
                    // one might try to check if a callee can be found
                    // const SVFFunction* callee = SVFUtil::getCallee(inst);
                    // will return nullptr if called function is set "at runtime"
                    // by calling an address -> LLVM can not derive this in most cases
                    // heavily used in linux kernel modules

                    SVF::CallSite cs = SVFUtil::getSVFCallSite(inst);

                    // check if this function call has at least 7 arguments
                    // TODO: can be further stip this down? e.g. same type for 7 parameters?

                    // Problem: if we have simple arithmetic influencing the SMC ID
                    // and we do not have the actual constant in the bitcode
                    // we will not get SMC ID right completely...
                    // we solve this partially by listening on arithemtic instructions

                    // this works for intel kernel
                    if(cs.arg_size() >= 5)    {
                       //cout << "\n######\nCallsite: " << cs.getInstruction()->toString() << "\n";
                        const SVFFunction *calledF = cs.getCalledFunction();
                        const SVFFunction *callerF = cs.getCaller();

                        if(callerF != NULL)  {
                           //cout << "Caller: " << callerF->getName() << "\n";
                        }
                        if(calledF != NULL)  {
                           //cout << "Potential CallSite: " << calledF->getName() << "\n";
                        }
                        //const SVF::SVFValue *x0 = cs.getArgument(0);
                       //cout << "Potential x0 of CallSite: " << x0->toString() << " at " << x0->getSourceLoc() << "\n";
                        
                        candidateSmcCS.push_back(cs);
                    }
                    else if(cs.arg_size() >= 4)   {
                        // this is needed for huawei kernel
                        // we only have 4 arguments there
                        const SVF::SVFValue *x0 = cs.getArgument(0);
                        if(cs.getCalledFunction() != NULL)  {
                           //cout << "Potential CallSite: " << cs.getCalledFunction()->getName() << "\n";
                        }
                        //cout << "Potential x0 of CallSite: " << x0->toString() << " at " << x0->getSourceLoc() << "\n";
                        if(x0->isConstDataOrAggData())  {
                           //cout << "Adding because first param is constant... x1: " << cs.getArgument(1)->toString() << "\n";
                            candidateSmcCS.push_back(cs);
                        }
                    }
                    string iname = cs.getInstruction()->toString();
                    if (iname.find("smc") != std::string::npos) {
                       //cout << "Potential CallSite because of instruction name:" << iname << "\n";
                        candidateSmcCS.push_back(cs);
                    }
                }
            }

        }
    }
    // go through all candidateSmcCs and ensure that only the "deepest" functions are part of it
    for(std::list<CallSite>::iterator currs = candidateSmcCS.begin(); currs != candidateSmcCS.end(); currs++)    {
        if(currs->getCalledFunction() != NULL)  {
            for(std::list<CallSite>::iterator cs = candidateSmcCS.begin(); cs != candidateSmcCS.end(); cs++)    {
                if(cs->getCaller()->getName() == currs->getCalledFunction()->getName())   {
                   //cout << "Found upper function to delete: " << currs->getInstruction()->toString() << "\n";
                    candidateSmcCS.erase(currs++);
                    break;
                }
            }
        }
    }
    return candidateSmcCS;
}

// IN: some metadata linked to a SVFValue which is on the path backward from a SMC param + offset
// OUT: the base type
// TODO: maybe we can add a heuristic which enables us to look at the variable name
// and if some "address" is in the local variable name -> add addr to type?
llvm::DIType *GetBaseTypeFromMetadata(const llvm::Metadata *md, u32_t offset)    {
    std::string str;
    raw_string_ostream rawstr(str);

    rawstr << "MetaLLVM: ";
    md->print(rawstr);
    rawstr << "\n";

    DIType *dit = nullptr;

    // TODO: also consider other varaible kinds
    if(md->getMetadataID() == md->DILocalVariableKind || md->getMetadataID() == md->DIGlobalVariableKind)  {
        DIVariable *var = (DIVariable *)md;
        dit = var->getType();
        // if it is a pointer - try to deref it
        while(dit != nullptr && dit->getMetadataID() == dit->DIDerivedTypeKind && (dit->getTag() == dwarf::DW_TAG_pointer_type || dit->getTag() == dwarf::DW_TAG_const_type || dit->getTag() == dwarf::DW_TAG_typedef))    {
            DIDerivedType *didt = (DIDerivedType *)dit;
            rawstr << "DerivedType 1: ";
            didt->print(rawstr);
            rawstr << "\n";

            // directly accessing the basetype with getBaseType()
            // leads to crashes when it is null... so check before
            // trying to check before with didt->getNumOperands()
            // also fails as this always? returns 6...
            // if we checked previously that we are a pointer type its ok

            if(didt->getRawBaseType() == NULL) {
                rawstr << "Nullptr found...\n";
                break;
            }
            else    {
                rawstr << "Some pointer found...\n";
                dit = didt->getBaseType();
            }
        }
        // this should not be a pointer anymore (except if nullptr)
        // check for struct TODO: make sure to be a struct
        if(dit != nullptr && dit->getMetadataID() == dit->DICompositeTypeKind && dit->getTag() == dwarf::DW_TAG_structure_type)    {
            DICompositeType *dic = (DICompositeType *)dit;
            rawstr << "CompositeType: ";
            dic->print(rawstr);
            rawstr << "\n";
            rawstr << "Offset: " << offset << "\n";
            if(dic->getRawElements() != NULL)   {
                DINodeArray els = dic->getElements();
                // TODO: this does not work if we have structs in structs
                // offset is not the field offset but rather the actual byte offset in memory
                if(dic->getElements().size() > offset)  {
                    dit = (DIType *)els[offset];
                }
                else    {
                    rawstr << "Some wrong offset?\n";
                    dit = (DIType *)els[0];
                }
            }
            //cout << rawstr.str() << "\n";
            //cout.flush();
            while(dit != nullptr && dit->getMetadataID() == dit->DIDerivedTypeKind && dit->getTag() != dwarf::DW_TAG_typedef)    {
                DIDerivedType *didt = (DIDerivedType *)dit;
                rawstr << "DerivedType 2: ";
                didt->print(rawstr);
                rawstr << "\n";

                // directly accessing the basetype with getBaseType()
                // leads to crashes when it is null... so check before
                // trying to check before with didt->getNumOperands()
                // also fails as this always? returns 6...

                if(didt->getRawBaseType() == NULL) {
                    rawstr << "Nullptr found...\n";
                    break;
                }
                else    {
                    dit = didt->getBaseType();
                }
            }
        }
        if(dit != nullptr && dit->getMetadataID() == dit->DICompositeTypeKind && dit->getTag() == dwarf::DW_TAG_array_type)    {
            DICompositeType *dic = (DICompositeType *)dit;
            dit = dic->getBaseType();
        }
        
        rawstr << "Base Type: ";
        if(dit != nullptr)  {
            dit->print(rawstr);
        }
    }
    //cout << rawstr.str() << "\n";
    return dit;
}

// input a SVFValue (previously found RootDef from SMC parameter usage)
// output Type of that Value based on usage in llvm dbg intrinsic functions
// the connection between a SVFValue and some intrinsic dbg function is
// not easy to find (for some there is even not dbg call)... so we do this by matching 
// source line number
// TODO: we do not find metdata for any global variables this way... ?
DIType *GetTypeFromDbgMetadata(SVFModule *svfModule, const SVFValue *v, u32_t offset)   {
    DIType *retType = nullptr;

    // we identify potential intrinsic llvm callsites by going through all instructions
    for (SVFModule::const_iterator F = svfModule->begin(), E = svfModule->end(); F != E; ++F)  {
        const SVFFunction *curr = (*F);
        // go through each basic block
        for(SVFFunction::const_iterator B = curr->begin(), BE = curr->end(); B != BE; ++B)  {
            const SVFBasicBlock *curr_bb = (*B);
            // go through each instruction
            for(SVFBasicBlock::const_iterator I = curr_bb->begin(), J = curr_bb->end(); I != J; ++I)    {
                const SVFInstruction *inst = (*I);

                // current instruction is an intrinsic callsite
                if (SVFUtil::isa<SVFCallInst>(inst))   {
                    const SVFCallInst *call = SVFUtil::dyn_cast<SVFCallInst>(inst);
                    const SVFFunction *func = call->getCalledFunction();
                    if(func && func->isIntrinsic()) {
                        if(call->arg_size() > 2)   {
                            // the value
                            //const SVFValue *currV = call->getArgOperand(0);
                            // the metadata
                            const SVFValue *currM = call->getArgOperand(1);

                            // TODO: only matching with source code line will result
                            // in getting also other variables defined there
                            // maybe also compare llvm value somehow?
                            size_t toSubStr = call->getSourceLoc().find(" cl:", 0);
                            std::string callSLOC = call->getSourceLoc().substr(0, toSubStr);
                            std::string valueSLOC = v->getSourceLoc().substr(0, toSubStr);
                            if(callSLOC == valueSLOC)  {
                                //cout << "Orig Value: " << v->toString() << " SLOC: " << valueSLOC << "\n";
                                //cout << "Intrinsic Function call: " << call->toString() << " SLOC: " << callSLOC << "\n";
                                if(SVFUtil::isa<SVF::SVFMetadataAsValue>(currM))    {
                                    
                                    // SVF can not handle metadata - so we fallback to LLVM instead
                                    const llvm::MetadataAsValue *llvmcurrM = (const llvm::MetadataAsValue *)LLVMModuleSet::getLLVMModuleSet()->getLLVMValue(currM);
                                    const llvm::Metadata *meta = llvmcurrM->getMetadata();
                                    retType = GetBaseTypeFromMetadata(meta, offset);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return retType;
}

// get argument parameter nodes from SINK smc callsites
Map<unsigned int, FIFOWorkList<const VFGNode *>> getcandidateArgumentVFGNodes(SVFModule* svfModule, ICFG* icfg, SVFG* svfg, std::list<SVF::CallSite> callsite)   {
    // this is a singleton
    SVFIR* pag = SVFIR::getPAG();
    
    Map<unsigned int, FIFOWorkList<const VFGNode *>> argsMap;

    // iterate over all callsites
    for(std::list<CallSite>::iterator cs = callsite.begin(); cs != callsite.end(); cs++)    {
        string iname = cs->getInstruction()->toString();
        //cout << "Arg extraction: Current Callside: " << iname << "\n";
        
        int assemblerCall = 0;
        int assemblerCallwithPointer = 0;
        if (iname.find("asm sideeffect") != std::string::npos) {
           //cout << "CallSite seems to be an inline assembly..." << iname << "\n";
            assemblerCall = 1;
        }

        // go through all arguments of the callsite
        for(unsigned int i = 0; i < cs->arg_size(); i++)    {
            // get LLVM value and PAG Node
            const SVF::SVFValue *arg_value = cs->getArgOperand(i);
            PAGNode *pNode = pag->getGNode(pag->getValueNode(arg_value));
            // get ICFG Node
            const CallICFGNode* callBlockNode = icfg->getCallICFGNode(cs->getInstruction());
            // we have Value and Location so we can get VFGNode
            const VFGNode* actual_param_vnode = svfg->getActualParmVFGNode(pNode, callBlockNode);
           //cout << "Arg extraction: IDX: " << i << " Value: " << arg_value->toString() << "\n";
            // get type via metadata
            /*DIType *argtype = GetTypeFromDbgMetadata(svfModule, arg_value, i);
            if(argtype != nullptr)  {
               //cout << "Type via Metadata: " << argtype->getName().str() << "\n";
            }
           //cout << "Type LLVM: " << arg_value->getType()->toString() << "\n";
            if(arg_value->getType()->isSingleValueType())  {
               //cout << "Single value\n";
            }
            if(arg_value->getType()->isPointerTy())  {
               //cout << "Pointer value\n";
                if(arg_value->getType()->getTypeInfo()->getOriginalElemType(0)->isPointerTy())   {
                   //cout << "Inside Pointer value\n";
                   //cout << arg_value->getType()->getTypeInfo()->getOriginalElemType(0)->toString() << "\n";
                }

                u32_t nelements = arg_value->getType()->getTypeInfo()->getNumOfFlattenElements();
               //cout << "Number of Elements: " << nelements << "\n";
                //cout << "Type of first Element: " << arg_value->getType()-> << "\n";
                //getType()->getTypeInfo()->getFlattenFieldTypes()[0]->toString() << "\n";
            }*/
            
            if(assemblerCall == 1)   {
                if(arg_value->getType()->isPointerTy())  {
                    assemblerCallwithPointer = 1;
                    // as we can not parse assembler code in llvm we just set all params as this node
                    argsMap[0].push(actual_param_vnode);
                    argsMap[1].push(actual_param_vnode);
                    argsMap[2].push(actual_param_vnode);
                    argsMap[3].push(actual_param_vnode);
                    argsMap[4].push(actual_param_vnode);
                    argsMap[5].push(actual_param_vnode);
                    argsMap[6].push(actual_param_vnode);
                }
                else if(arg_value->getType()->isSingleValueType() && assemblerCallwithPointer == 1)  {
                    // if we see a single value type and we had a pointer call we assume it to
                    // be the funcID -> register x0
                    argsMap[0].push(actual_param_vnode);
                }
            }
            else    {
                // we assume x0 register to be also the first parameter etc...
                argsMap[i].push(actual_param_vnode);
            }
        }
    }

    return argsMap;
}

const SVFValue *backwardDFSUntilRootDef(SVFModule *svfModule, const VFGNode *vNode, Set<const VFGNode *> *traverseBlacklist, unsigned int idx, Set<const SVFBasicBlock *> *constValuesBB, Map<const SVF::SVFBasicBlock *, list<smcArg>> *smcArgMap) {

    const SVFValue *retValue = nullptr;

    // already visited
    if(traverseBlacklist->find(vNode) != traverseBlacklist->end())  {
        return retValue;
    }

   //cout << "BACKWARD Start vNode: " << vNode->toString() << "\n";
   //cout.flush();

    // base case - we are at an edge node which indicates a root definition site
    if(!vNode->hasIncomingEdge())  {
        if(SVFUtil::isa<AddrVFGNode>(vNode))    {
            const AddrVFGNode *addrNode = SVFUtil::dyn_cast<AddrVFGNode>(vNode);
            const AddrStmt *addrstmt = SVFUtil::cast<AddrStmt>(addrNode->getPAGEdge());
            const SVFBasicBlock *bb = addrNode->getICFGNode()->getBB();
           //cout << addrstmt->toString() << "\n";
           //cout.flush();
            //cout << "RootDef: " << addrstmt->toString() << "\n";
            //cout << "LLVM Type: " << addrstmt->getValue()->getType()->toString() << "\n";
            //cout << "LHSVar ID: " << addrstmt->getLHSVarID() << "\n";
            //cout << "SVFValue: " << addrstmt->getLHSVar()->getValue()->toString() << "\n";
            /*if(addrstmt->getValue() != NULL)    {
                //cout << "TEST: " << addrstmt->getValue()->toString() << "\n";
                //cout.flush();
            }*/
            if(bb != nullptr)   {
                DIType *argtype = GetTypeFromDbgMetadata(svfModule, addrstmt->getValue(), 0);

                unsigned long c = UINT64_MAX;
                smcArg a = { idx, c, argtype };

                bool added = false;
                for(list<smcArg>::iterator iter = (*smcArgMap)[bb].begin(); iter != (*smcArgMap)[bb].end(); iter++) {
                    if((*iter) == a)    {
                        (*iter).type = argtype;
                        added = true;
                        break;
                    }
                }
                if (!added)   {
                    (*smcArgMap)[bb].push_back(a);
                }
               //cout << "Added new SmcArg for Idx: " << idx << " with Node: " << addrNode->toString() << " BB: " << bb->toString() << "\n";
                    
                if(argtype != nullptr)  {
                    std::string str;
                    raw_string_ostream rawstr(str);
                    argtype->print(rawstr);
                   //cout << "Found Type: " << rawstr.str() << "\n";
                }
            }
            retValue = addrstmt->getValue();
            //GetTypeFromDbgMetadata(svfModule, retValue, 0);
        }
        else if(SVFUtil::isa<ActualParmVFGNode>(vNode))   {
            const ActualParmVFGNode *actualParamNode = SVFUtil::dyn_cast<ActualParmVFGNode>(vNode);
            const SVFValue *apValue = actualParamNode->getValue();
            const SVFBasicBlock *bb = actualParamNode->getICFGNode()->getBB();

            if(apValue->isConstDataOrAggData())  {
                //constValues->insert(getConstValue(apValue));
                /* Problem
                    We currently get overlapping of two calls ln:198 zynqmp.c
                    and ln:352 -> both lead to the same constant through parameter
                    -> this leads to overwriting
                    Also:
                        It seems that we can not differentiate between arg0 and arg1
                        as it seems that there is indirect value flow in the VFG...
                        Why is this?
                        This is hard to fix... only option may be to do backward/forward offset tracking
                */
               // simple idea: if we get the same const as with idx=0 just do not use it
               // Fix: acutally this can be fixed (mostly) by the flag "-model-arrays"

                unsigned long c = getConstValue(apValue);
                smcArg a = { idx, c, nullptr };
                bool added = false;
                for(list<smcArg>::iterator iter = (*smcArgMap)[bb].begin(); iter != (*smcArgMap)[bb].end(); iter++) {
                    if((*iter) == a)    {
                        // only write constant if not already init
                        if((*iter).constant == UINT64_MAX)  {
                            (*iter).constant = c;
                        }
                        added = true;
                        break;
                    }
                }
                if (!added)   {
                    (*smcArgMap)[bb].push_back(a);
                }
               //cout << "Added new SmcArg for Idx: " << idx << " with Node: " << actualParamNode->toString() << " BB: " << bb->toString() << "\n";
                retValue = apValue;
                constValuesBB->insert(bb);
            }
            //retValue = apValue;
        }
        return retValue;
    }
    else    {
        // mark as visited
        traverseBlacklist->insert(vNode);
        for (VFGNode::const_iterator it = vNode->InEdgeBegin(), eit = vNode->InEdgeEnd(); it != eit; ++it)  {
            VFGEdge *edge = *it;
            const VFGNode *preNode = edge->getSrcNode();

            // recursive call
            const SVFValue *v = backwardDFSUntilRootDef(svfModule, preNode, traverseBlacklist, idx, constValuesBB, smcArgMap);
            if(v == nullptr)    {
                continue;
            }
            
           //cout << "BACKWARD ret vNode: " << vNode->toString() << "\n";
           //cout.flush();

            if(SVFUtil::isa<BinaryOPVFGNode>(vNode))   {
                const BinaryOPVFGNode *bopNode = SVFUtil::dyn_cast<BinaryOPVFGNode>(vNode);
                //const SVFBasicBlock *bb = bopNode->getICFGNode()->getBB();
                const SVFValue *op1 = bopNode->getOpVer(0)->getValue();
                //const SVFValue *op2 = bopNode->getOpVer(1)->getValue();
                std::string bopstr = bopNode->getValue()->toString();
                //cout << bopNode->toString() << "\n";
                //cout.flush();
                // if some constants were found along the way we might have to do arithmetic on them
                if(!constValuesBB->empty())   {
                    //cout << "Found " << constValuesBB->size() << " const values with BB for idx: " << idx << "\n";
                    //cout.flush();
                    if(bopstr.find("= or") < bopstr.length())   {
                        //cout << "Op 1: " << op1->toString() << "\n";
                        //cout << "Op 2: " << op2->toString() << "\n";
                        if(op1->isConstDataOrAggData()) {
                            unsigned long opconst = getConstValue(op1);
                            
                            for(Set<const SVFBasicBlock *>::iterator iter = constValuesBB->begin(); iter != constValuesBB->end(); iter++)  {
                                for(list<smcArg>::iterator it = (*smcArgMap)[*iter].begin(); it != (*smcArgMap)[*iter].end(); it++)    {
                                    if((*it).idx == idx)    {
                                        (*it).constant = (opconst | (*it).constant);
                                    }
                                }
                            }
                        }
                        // TODO: do we want to add multiple binary operations?
                        /*else if(op2->isConstDataOrAggData())    {

                        }*/
                        constValuesBB->clear();
                    }
                }
                // just pass original value through
                retValue = v;
            }

            // as we have indirect value flow we also get store nodes backward
            if(SVFUtil::isa<StoreVFGNode>(vNode))    {
                const StoreVFGNode *storeNode = SVFUtil::dyn_cast<StoreVFGNode>(vNode);
                const StoreStmt *storestmt = SVFUtil::cast<StoreStmt>(storeNode->getPAGEdge());
               //cout << storestmt->toString() << "\n";
                const SVFBasicBlock *bb = storeNode->getICFGNode()->getBB();
                //cout << "ICFG: " << bb->toString() << "\n";
                
                if(storestmt->getRHSVar()->getValue()->isConstDataOrAggData())  {
                    //cout << "Constant Src Value: " << storestmt->getRHSVar()->getValue()->toString() << "\n";
                    unsigned long c = getConstValue(storestmt->getRHSVar()->getValue());
                    smcArg a = { idx, c, nullptr };
                    bool added = false;
                    for(list<smcArg>::iterator iter = (*smcArgMap)[bb].begin(); iter != (*smcArgMap)[bb].end(); iter++) {
                        if((*iter) == a)    {
                            // only write constant if not already init
                            if((*iter).constant == UINT64_MAX)  {
                                (*iter).constant = c;
                            }
                            added = true;
                            break;
                        }
                    }
                    if (!added)   {
                        (*smcArgMap)[bb].push_back(a);
                    }
                   //cout << "Added new SmcArg for Idx: " << idx << " with Node: " << storeNode->toString() << " BB: " << bb->toString() << "\n";
                }
                // get destination value and try to get type
                retValue = storestmt->getLHSVar()->getValue();
                //cout << retValue->toString() << "\n";
                //cout.flush();
            }

            if(SVFUtil::isa<GepVFGNode>(vNode))    {
                const GepVFGNode *gepNode = SVFUtil::dyn_cast<GepVFGNode>(vNode);
                const GepStmt *gepstmt = SVFUtil::cast<GepStmt>(gepNode->getPAGEdge());
               //cout << gepstmt->toString() << "\n";
                const SVFBasicBlock *bb = gepNode->getICFGNode()->getBB();
                //cout << "ICFG: " << bb->toString() << "\n";

                //cout << "Orig Value: " << v->toString() << "\n";
                //cout.flush();
                
                // Problem: Arrays seem not to be modeled by SVF
                // Solution: can be turned on by option "-model-arrays"
                // is it even necessary to get the offset of the array if we just want to get the type?
                // no - we can just get the type of the array
                unsigned int offset = 0;
                // if we do not have a constant offset we just use default offset 0... is this a problem?
                // we will not get the correct member of that struct access... can lead to "useless" type information
                if(gepstmt->isConstantOffset()) {
                    offset = gepstmt->accumulateConstantOffset();
                }
                //unsigned int offset = gepstmt->accumulateConstantOffset();
                //cout << "GepStmt Offset: " << offset << "\n";
                //cout.flush();


                DIType *argtype = nullptr;
                // get metadata either from global directly or by matching with debug intrinsic usage
                if(SVFUtil::isa<SVFGlobalValue>(v))   {
                    const SVFGlobalValue *gvalue = SVFUtil::dyn_cast<SVFGlobalValue>(v);
                    const llvm::GlobalVariable *gvar = (const llvm::GlobalVariable *)LLVMModuleSet::getLLVMModuleSet()->getLLVMValue(gvalue);

                    const llvm::Metadata *meta = gvar->getMetadata("dbg");
                    if(meta != nullptr) {
                        if(meta->getMetadataID() == meta->DIGlobalVariableExpressionKind)   {
                            DIGlobalVariableExpression *digvarexp = (DIGlobalVariableExpression *)meta;
                            DIGlobalVariable *digvar = digvarexp->getVariable();
                            argtype = GetBaseTypeFromMetadata(digvar, offset);
                        }
                    }
                }
                else    {
                    argtype = GetTypeFromDbgMetadata(svfModule, v, offset);
                }

                unsigned long c = UINT64_MAX;
                smcArg a = { idx, c, argtype };

                bool added = false;
                for(list<smcArg>::iterator iter = (*smcArgMap)[bb].begin(); iter != (*smcArgMap)[bb].end(); iter++) {
                    if((*iter) == a)    {
                        (*iter).type = argtype;
                        added = true;
                        break;
                    }
                }
                if (!added)   {
                    (*smcArgMap)[bb].push_back(a);
                }
               //cout << "Added new SmcArg for Idx: " << idx << " with Node: " << gepNode->toString() << " BB: " << bb->toString() << "\n";
                
                if(argtype != nullptr)  {
                    std::string str;
                    raw_string_ostream rawstr(str);
                    argtype->print(rawstr);
                   //cout << "Found Type: " << rawstr.str() << "\n";
                }
            }
            // do we even need load? - if only access to struct maybe not... but can not be assumed
            if(SVFUtil::isa<LoadVFGNode>(vNode))    {
                const LoadVFGNode *loadNode = SVFUtil::dyn_cast<LoadVFGNode>(vNode);
                const LoadStmt *loadstmt = SVFUtil::cast<LoadStmt>(loadNode->getPAGEdge());
               //cout << loadstmt->toString() << "\n";
                const SVFBasicBlock *bb = loadNode->getICFGNode()->getBB();
                //cout << "ICFG: " << bb->toString() << "\n";

                //cout << "Orig Value: " << v->toString() << "\n";

                //cout.flush();

                // when we have a load we just pass the original memory alloca through
                // for now TODO: what if we never access via gep?
                retValue = v;

                // get source value and try to get type
                //cout << "Trying to get metadata match with RHS: " << loadstmt->getRHSVar()->getValue()->toString() << "\n";
                //cout.flush();
                DIType *argtype = GetTypeFromDbgMetadata(svfModule, loadstmt->getRHSVar()->getValue(), 0);

                unsigned long c = UINT64_MAX;
                smcArg a = { idx, c, argtype };

                bool added = false;
                for(list<smcArg>::iterator iter = (*smcArgMap)[bb].begin(); iter != (*smcArgMap)[bb].end(); iter++) {
                    if((*iter) == a)    {
                        (*iter).type = argtype;
                        added = true;
                        break;
                    }
                }
                if (!added)   {
                    (*smcArgMap)[bb].push_back(a);
                }
               //cout << "Added new SmcArg for Idx: " << idx << " with Node: " << loadNode->toString() << " BB: " << bb->toString() << "\n";
                
                if(argtype != nullptr)  {
                    std::string str;
                    raw_string_ostream rawstr(str);
                    argtype->print(rawstr);
                   //cout << "Found Type: " << rawstr.str() << "\n";
                }

                /*if(SVFUtil::isa<SVFPointerType>(v->getType()))    {
                    //const SVFPointerType *p = SVFUtil::dyn_cast<SVFPointerType>(v->getType());
                    //cout << p->getPtrElementType()->toString() << "\n";
                    //retType = p;
                }*/
            }
            if(SVFUtil::isa<CopyVFGNode>(vNode))    {
                // just pass original value through
                retValue = v;
            }
        }
        // remove from visited
        traverseBlacklist->erase(vNode);
    }
    return retValue;
}

const SVFType *extractType(SVFModule* svfModule, const VFGNode *node, unsigned int idx, Map<const SVF::SVFBasicBlock *, list<smcArg>> *smcArgMap)  {
    const SVFType *t = nullptr;
    const SVFValue *v = node->getValue();

    // we have a direct constant here
    if(v->isConstDataOrAggData())   {
        const SVF::SVFBasicBlock *bb = node->getICFGNode()->getBB();
        unsigned long c = getConstValue(v);
        smcArg a = { idx, c, nullptr };
        bool added = false;
        for(list<smcArg>::iterator iter = (*smcArgMap)[bb].begin(); iter != (*smcArgMap)[bb].end(); iter++) {
            if((*iter) == a)    {
                // only write constant if not already init
                if((*iter).constant == UINT64_MAX)  {
                    (*iter).constant = c;
                }
                added = true;
                break;
            }
        }
        if (!added)   {
            (*smcArgMap)[bb].push_back(a);
        }
        t = v->getType();
    }
    else    {
        // try to get type info through backward search
        Set<const VFGNode *> traverseBlacklist;
        Set<const SVF::SVFBasicBlock *> constValuesBB;
        const SVFValue *rootdef = backwardDFSUntilRootDef(svfModule, node, &traverseBlacklist, idx, &constValuesBB, smcArgMap);
        if(rootdef != nullptr)  {
            t = rootdef->getType();
        }
    }

    return t;
}

int main(int argc, char ** argv)
{
    // check for ENV variable indicating the target outfile
    char *outpath = getenv("SMFUZZ_HARNESSDATA_PATH");
    // of set a default in the out directory
    if(outpath == NULL) {
        outpath = (char *)"/in/harnessdata.csv";
    }

    int arg_num = 0;
    char **arg_value = new char*[argc];
    std::vector<std::string> moduleNameVec;
    LLVMUtil::processArguments(argc, argv, arg_num, arg_value, moduleNameVec);
    cl::ParseCommandLineOptions(arg_num, arg_value,
                                "Whole Program Points-to Analysis\n");

    if (Options::WriteAnder == "ir_annotator")
    {
        LLVMModuleSet::getLLVMModuleSet()->preProcessBCs(moduleNameVec);
    }

    SVFModule* svfModule = LLVMModuleSet::getLLVMModuleSet()->buildSVFModule(moduleNameVec);

    /// Build Program Assignment Graph (SVFIR)
    SVFIRBuilder builder(svfModule);
    SVFIR* pag = builder.build();

    /// Create Andersen's pointer analysis
    Andersen* ander = AndersenWaveDiff::createAndersenWaveDiff(pag);
    // is there any important difference?
    //SVF::FlowSensitive* fls = FlowSensitive::createFSWPA(pag);

    /// Call Graph
    PTACallGraph* callgraph = ander->getPTACallGraph();

    /// ICFG
    ICFG* icfg = pag->getICFG();

    /// Value-Flow Graph (VFG)
    VFG* vfg = new VFG(callgraph);

    /// Sparse value-flow graph (SVFG)
    SVFGBuilder svfBuilder(true);
    SVFG* svfg = svfBuilder.buildFullSVFG(ander);

    // TODO: this has to be given a prior knowledge
    // This is a map of known memtransfer functions and their counterparts
    // e.g., some fifo_in and fifo_out
    //Map<std::string, std::string> memTransferMap;
    //memTransferMap.insert(pair<std::string, std::string>("1st arg __kfifo_out ", "1st arg __kfifo_in "));

    // We get SMC types in steps:
    // 1. find function candidates and/or callsites for SMC
    //      These are potential SINKs
    //      We can not go down to the assembly smc instruction it is typically wrapped 
    //      in some function exported -> heuristic: candidates are functions/calls 
    //      with at least 7 parameters but this may be changed for other kernels
    //      Alternative: make this a manual step

    // IN: svfModule
    // OUT: List of SVF::Callsite all candidate SMC function callsites
    std::list<SVF::CallSite> candidateSmcCS = getSmcCallSiteCandidates(svfModule);
   //cout << "\nFound " << candidateSmcCS.size() << " candidate SMC Callsites\n";

    // 2. get all ActualParmVFGNode of each callsite (SINK)
    //      We go through each callsite and derive the corresponding ActualParamVFGNodes
    //      TODO: currently we just throw all argument nodes in one list
    //      BETTER: hold one list per callsite

    Map<unsigned int, FIFOWorkList<const VFGNode *>> argToSnks = getcandidateArgumentVFGNodes(svfModule, icfg, svfg, candidateSmcCS);
    
    // use the basic block as an ID for SMC tuples
    // each tuple is defined by arg idx, its type, and possible constant value
    Map<const SVF::SVFBasicBlock *, list<smcArg>> smcArgMap;

    for(unsigned int i = 0; i < argToSnks.size(); i++)  {
        //cout << "Arg Idx: " << i << " has " << argToSnks[i].size() << " candidate ArgumentNodes\n";

        FIFOWorkList<const VFGNode *> arglist = argToSnks[i];

        while(!arglist.empty())   {
            const VFGNode *currNode = arglist.pop();
           //cout << "Arg IDX: " << i << " CurrNode: " << currNode->toString() << "\n";
            //cout.flush();
            // write results in smcArgMap
            extractType(svfModule, currNode, i, &smcArgMap);
        }
    }
    //printSmcArgMap(&smcArgMap);

    dumpToCSV(&smcArgMap, outpath);

    // Problems:
    //  - backwardDFS can not just get potential new Sink nodes -> offset transfering not possible
    //      because we do not know corresponding actualret nodes
    //  - not here but: we need to implement reverseOffsetCheck in forwardDFS -> only add StoreNodes when offsets match

    // clean up memory
    delete vfg;
    //delete svfg;
    AndersenWaveDiff::releaseAndersenWaveDiff();
    //FlowSensitive::releaseFSWPA();
    SVFIR::releaseSVFIR();

    //LLVMModuleSet::getLLVMModuleSet()->dumpModulesToFile(".svf.bc");
    SVF::LLVMModuleSet::releaseLLVMModuleSet();

    llvm::llvm_shutdown();
    return 0;
}

