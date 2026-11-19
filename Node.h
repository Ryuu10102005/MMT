#ifndef __NODE_H
#define __NODE_H

#include <omnetpp.h>
#include <queue>

using namespace omnetpp;

enum SigKind { SIG_START = 1, SIG_END = 2, SIG_RESULT = 3 };
enum Protocol { CSMACD, ALOHA, SLOTTED };
enum NodeState { ST_IDLE, ST_WAIT, ST_TRANSMIT, ST_JAM, ST_BACKOFF, ST_SETTLING };

class Node : public cSimpleModule
{
  protected:
    Protocol protocol;
    simtime_t frameTime, jamTime, slotTime, propagationTime, alohaSlotTime;
    double meanIat;
    int maxAttempts, maxBackoffExp, retxWindow, queueLimit;

    NodeState state = ST_IDLE;
    std::queue<simtime_t> q;
    int rxCount = 0;
    int attempts = 0;
    long attemptSerial = 0;

    cMessage *genTimer = nullptr;
    cMessage *txEnd = nullptr;
    cMessage *jamEnd = nullptr;
    cMessage *backoffTimer = nullptr;
    cMessage *startTimer = nullptr;
    cMessage *warmupTimer = nullptr;

    long generated = 0, blocked = 0, success = 0, collisions = 0, dropped = 0, retx = 0;
    long txAttempts = 0, resolved = 0, initialPending = 0, backoffs = 0;
    long maxBackoffDraw = 0, maxBackoffExponent = 0, waited = 0;
    double delaySum = 0;
    bool deterministic = false;
    simsignal_t txStartSig, backoffSig, backoffExponentSig;
    simsignal_t delaySig, attemptsSig;

    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    void onGenerate();
    void onBusSignal(cMessage *msg);
    void onTxEnd();
    void onJamEnd();
    void onCollisionDetected();
    void onBackoffEnd();

    void beginService();
    void attemptTx();
    void startTx();
    void sendSignal(int kind);
    void startBackoffCsma();
    void startBackoffAloha();
    void frameSuccess();
    void dropFrame();
    void nextFrame();
    bool measuring();

  public:
    virtual ~Node();
};

#endif
