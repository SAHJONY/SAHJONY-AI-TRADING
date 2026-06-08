module.exports = class {
  async messagesCreate() { return { content: [{ text: 'Stub response' }] }; }
  constructor(config) { this.config = config; }
  messages = { create: async () => ({ content: [{ text: 'Stub response' }] }) };
};