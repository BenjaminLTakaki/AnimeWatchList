const mongoose = require('mongoose');
const { v4: uuidv4 } = require('uuid');

const questionSchema = new mongoose.Schema({
  _id: {
    type: String,
    default: uuidv4,
    required: true,
  },
  question: {
    type: String,
    required: true
  },
  options: [{
    type: String,
    required: true
  }],
  correctAnswer: {
    type: String,
    required: true
  },
  explanation: {
    type: String,
    required: false
  }
});

const Question = mongoose.model('Question', questionSchema);

module.exports = Question; 