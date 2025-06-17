const mongoose = require('mongoose');
const { v4: uuidv4 } = require('uuid');

const quizSchema = new mongoose.Schema({
  _id: {
    type: String,
    default: uuidv4,
    required: true,
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    required: false
  },
  subject: {
    type: String,
    required: true
  },
  createdBy: {
    type: String,
    ref: 'User',
    required: true
  },
  questions: [{
    type: String,
    ref: 'Question'
  }],
  isPublic: {
    type: Boolean,
    default: true
  }
}, { timestamps: true });

const Quiz = mongoose.model('Quiz', quizSchema);

module.exports = Quiz; 