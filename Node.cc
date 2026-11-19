#include "Node.h"
#include <cmath>
#include <algorithm>

Define_Module(Node);

Node::~Node()
{
    cancelAndDelete(genTimer);
    cancelAndDelete(txEnd);
    cancelAndDelete(jamEnd);
    cancelAndDelete(backoffTimer);
    cancelAndDelete(startTimer);
    cancelAndDelete(warmupTimer);
}

void Node::initialize()
{
    std::string p = par("protocol").stdstringValue();
    if (p == "csmacd") protocol = CSMACD;
    else if (p == "aloha") protocol = ALOHA;
    else if (p == "slotted") protocol = SLOTTED;
    else throw cRuntimeError("Unknown protocol '%s'", p.c_str());

    double bitrate = par("bitrate").doubleValue();
    if (!std::isfinite(bitrate) || bitrate <= 0 || par("frameBits").intValue() <= 0 || par("jamBits").intValue() <= 0 || par("slotBits").intValue() <= 0)
        throw cRuntimeError("Bitrate must be finite and positive; frame/jam/slot sizes must be positive");
    frameTime = SimTime(par("frameBits").intValue() / bitrate);
    jamTime   = SimTime(par("jamBits").intValue() / bitrate);
    maxAttempts   = par("maxAttempts");
    maxBackoffExp = par("maxBackoffExp");
    retxWindow    = par("retxWindow");
    queueLimit    = par("queueLimit");
    deterministic = par("deterministic");
    if (maxAttempts < 1 || maxBackoffExp < 0 || maxBackoffExp > 20 || retxWindow < 1 || queueLimit < 1)
        throw cRuntimeError("Invalid retry, backoff or queue parameters");

    int N = getParentModule()->par("numNodes");
    simtime_t maxProp = SimTime(getParentModule()->getSubmodule("bus")->par("maxPropDelay").doubleValue());
    propagationTime = maxProp;
    alohaSlotTime = frameTime + maxProp;

    slotTime = std::max(SimTime(par("slotBits").intValue() / bitrate), maxProp * 2.0);

    if (frameTime <= SIMTIME_ZERO || jamTime <= SIMTIME_ZERO || slotTime <= SIMTIME_ZERO)
        throw cRuntimeError("Transmission durations must be positive at the current simtime resolution");

    if (maxProp < SIMTIME_ZERO || N < 1)
        throw cRuntimeError("Invalid propagation delay or node count");
    if (protocol == CSMACD && N > 1 && frameTime <= maxProp * 2.0)
        throw cRuntimeError("frameTime <= 2*maxPropDelay: khung qua ngan, CSMA/CD khong phat hien duoc va cham");

    double G = par("G");
    if (!std::isfinite(G) || G <= 0)
        throw cRuntimeError("G must be finite and positive");
    meanIat = frameTime.dbl() * N / G;
    if (!std::isfinite(meanIat) || meanIat <= 0 || SimTime(meanIat) <= SIMTIME_ZERO)
        throw cRuntimeError("Mean interarrival time must be finite and positive at the current simtime resolution");

    delaySig = registerSignal("delay");
    attemptsSig = registerSignal("attempts");
    txStartSig = registerSignal("txStart");
    backoffSig = registerSignal("backoffSlots");
    backoffExponentSig = registerSignal("backoffExponent");

    genTimer = new cMessage("gen");
    txEnd = new cMessage("txEnd");
    jamEnd = new cMessage("jamEnd");
    backoffTimer = new cMessage("backoff");
    startTimer = new cMessage("slotStart");
    startTimer->setSchedulingPriority(2);
    txEnd->setSchedulingPriority(-3);
    jamEnd->setSchedulingPriority(-3);
    warmupTimer = new cMessage("warmupSnapshot");
    warmupTimer->setSchedulingPriority(-10);
    scheduleAt(getSimulation()->getWarmupPeriod(), warmupTimer);

    double firstSeconds = deterministic ? par("firstArrival").doubleValue() : exponential(meanIat);
    if (!std::isfinite(firstSeconds) || firstSeconds < 0)
        throw cRuntimeError("firstArrival must be finite and nonnegative");
    simtime_t first = SimTime(firstSeconds);
    scheduleAt(first, genTimer);
}

bool Node::measuring()
{
    return simTime() >= getSimulation()->getWarmupPeriod();
}

void Node::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage()) {
        if (msg == genTimer) onGenerate();
        else if (msg == txEnd) onTxEnd();
        else if (msg == jamEnd) onJamEnd();
        else if (msg == backoffTimer) onBackoffEnd();
        else if (msg == startTimer) startTx();
        else if (msg == warmupTimer) initialPending = q.size();
    }
    else {
        onBusSignal(msg);
    }
}

void Node::onGenerate()
{
    if (!deterministic) scheduleAt(simTime() + exponential(meanIat), genTimer);
    if (measuring()) generated++;

    if ((int)q.size() >= queueLimit) {
        if (measuring()) blocked++;
        return;
    }
    q.push(simTime());

    if (state == ST_IDLE)
        beginService();
}

void Node::beginService()
{
    attempts = 0;
    attemptTx();
}

void Node::attemptTx()
{
    if (protocol == CSMACD) {
        if (rxCount > 0) { state = ST_WAIT; if (measuring()) waited++; }
        else startTx();
    }
    else if (protocol == ALOHA) {
        startTx();
    }
    else {
        int64_t ticks = alohaSlotTime.raw();
        int64_t now = simTime().raw();
        simtime_t t = SimTime::fromRaw(((now + ticks - 1) / ticks) * ticks);
        if (t > simTime()) { state = ST_WAIT; scheduleAt(t, startTimer); }
        else startTx();
    }
}

void Node::startTx()
{
    state = ST_TRANSMIT;
    attempts++;
    if (measuring()) { txAttempts++; if (attempts > 1) retx++; }
    emit(txStartSig, simTime());
    attemptSerial++;
    sendSignal(SIG_START);
    scheduleAt(simTime() + frameTime, txEnd);
}

void Node::sendSignal(int kind)
{
    cMessage *s = new cMessage(kind == SIG_START ? "start" : "end", kind);
    s->addPar("attemptId").setLongValue(attemptSerial);
    s->setSchedulingPriority(kind == SIG_END ? -4 : 0);
    send(s, "out");
}

void Node::onBusSignal(cMessage *msg)
{
    int kind = msg->getKind();
    if (kind == SIG_RESULT) {
        long serial = msg->par("attemptId").longValue();
        bool failed = msg->par("collided").boolValue();
        delete msg;
        // Jammed attempts are already resolved; their verdict may arrive
        // after a new backoff or attempt has started.
        if (serial != attemptSerial || state != ST_SETTLING) return;
        if (protocol == CSMACD && failed)
            throw cRuntimeError("CSMA/CD completed a physically collided frame without detection");
        if (measuring()) resolved++;
        if (!failed) frameSuccess();
        else {
            if (measuring()) collisions++;
            if (attempts >= maxAttempts) dropFrame();
            else startBackoffAloha();
        }
        return;
    }
    delete msg;
    if (kind == SIG_START) {
        rxCount++;
        if (state == ST_TRANSMIT) {
            if (protocol == CSMACD)
                onCollisionDetected();
        }
    }
    else {
        rxCount--;
        if (rxCount < 0) throw cRuntimeError("Unbalanced channel signals");
        if (rxCount == 0 && state == ST_WAIT && protocol == CSMACD)
            startTx();
    }
}

void Node::onCollisionDetected()
{
    cancelEvent(txEnd);
    state = ST_JAM;
    if (measuring()) { collisions++; resolved++; }
    scheduleAt(simTime() + jamTime, jamEnd);
}

void Node::onJamEnd()
{
    sendSignal(SIG_END);
    if (attempts >= maxAttempts) { dropFrame(); return; }
    startBackoffCsma();
}

void Node::startBackoffCsma()
{
    int n = std::min(attempts, maxBackoffExp);
    int k = intuniform(0, (1 << n) - 1, 1);
    ASSERT(k >= 0 && k < (1 << n));
    emit(backoffSig, (long)k);
    emit(backoffExponentSig, (long)n);
    if (measuring()) {
        backoffs++;
        maxBackoffDraw = std::max(maxBackoffDraw, (long)k);
        maxBackoffExponent = std::max(maxBackoffExponent, (long)n);
    }
    state = ST_BACKOFF;
    scheduleAt(simTime() + slotTime * k, backoffTimer);
}

void Node::onTxEnd()
{
    sendSignal(SIG_END);
    // All MACs await the same propagation-tail verdict before completion.
    state = ST_SETTLING;
}

void Node::startBackoffAloha()
{
    state = ST_BACKOFF;
    simtime_t unit = protocol == SLOTTED ? alohaSlotTime : frameTime;
    scheduleAt(simTime() + unit * intuniform(1, retxWindow, 1), backoffTimer);
}

void Node::onBackoffEnd()
{
    attemptTx();
}

void Node::frameSuccess()
{
    simtime_t created = q.front();
    q.pop();
    if (measuring()) {
        success++;
        delaySum += (simTime() - created).dbl();
        emit(delaySig, simTime() - created);
        emit(attemptsSig, (long)attempts);
    }
    nextFrame();
}

void Node::dropFrame()
{
    q.pop();
    if (measuring()) dropped++;
    nextFrame();
}

void Node::nextFrame()
{
    state = ST_IDLE;
    if (!q.empty())
        beginService();
}

void Node::finish()
{
    // A run may end before the warmup snapshot is reached. Its observation
    // window is empty, so use the ending inventory at both boundaries.
    if (warmupTimer->isScheduled()) initialPending = q.size();
    double T = (simTime() - getSimulation()->getWarmupPeriod()).dbl();
    recordScalar("generated", generated);
    recordScalar("blocked", blocked);
    recordScalar("success", success);
    recordScalar("collisions", collisions);
    recordScalar("dropped", dropped);
    recordScalar("retransmissions", retx);
    recordScalar("txAttempts", txAttempts);
    recordScalar("resolvedAttempts", resolved);
    recordScalar("initialPending", initialPending);
    recordScalar("finalPending", q.size());
    recordScalar("delaySum", delaySum);
    recordScalar("measurementTime", std::max(0.0, T));
    recordScalar("frameTime", frameTime.dbl());
    recordScalar("phyModelVersion", 2);
    recordScalar("propagationTime", propagationTime.dbl());
    recordScalar("alohaSlotTime", alohaSlotTime.dbl());
    recordScalar("frameBits", par("frameBits").intValue());
    recordScalar("backoffs", backoffs);
    recordScalar("maxBackoffDraw", maxBackoffDraw);
    recordScalar("maxBackoffExponent", maxBackoffExponent);
    recordScalar("carrierWaits", waited);
    ASSERT(initialPending + generated - blocked == success + dropped + (long)q.size());
    recordScalar("throughput", T > 0 ? success * frameTime.dbl() / T : 0.0);
}
